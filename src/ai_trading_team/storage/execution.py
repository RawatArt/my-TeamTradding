"""Append-only in-memory and SQLite persistence for M11 DEMO execution."""

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    DemoExecutionState,
    DemoSubmissionDisposition,
    ExecutionControlState,
)
from ai_trading_team.schemas.execution import (
    DemoExecutionApproval,
    DemoExecutionApprovalRevocation,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionEvent,
    DemoExecutionFailure,
    DemoExecutionPreflight,
    DemoExecutionRecord,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    ExecutionControlEvent,
    FreshRiskRevalidation,
)


class InMemoryDemoExecutionRepository:
    """Atomic claims and append-only lifecycle projections."""

    def __init__(self) -> None:
        self._acceptances: dict[str, DemoExecutionEnvironmentAcceptance] = {}
        self._approvals: dict[str, DemoExecutionApproval] = {}
        self._revocations: dict[str, DemoExecutionApprovalRevocation] = {}
        self._control_events: list[ExecutionControlEvent] = []
        self._records: dict[str, DemoExecutionRecord] = {}
        self._source_index: dict[str, str] = {}
        self._client_index: dict[str, str] = {}
        self._lock = RLock()

    def add_environment_acceptance(
        self, acceptance: DemoExecutionEnvironmentAcceptance
    ) -> None:
        with self._lock:
            if acceptance.acceptance_id in self._acceptances:
                raise ValueError("environment acceptance identity already exists")
            self._acceptances[acceptance.acceptance_id] = acceptance

    def add_approval(self, approval: DemoExecutionApproval) -> None:
        with self._lock:
            if approval.approval_id in self._approvals:
                raise ValueError("DEMO approval identity already exists")
            self._approvals[approval.approval_id] = approval

    def revoke_approval(self, revocation: DemoExecutionApprovalRevocation) -> None:
        with self._lock:
            if revocation.revocation_id in self._revocations:
                raise ValueError("approval revocation identity already exists")
            approval = self._approvals.get(revocation.approval_id)
            if approval is None or content_digest(approval) != revocation.approval_digest:
                raise ValueError("approval revocation does not match an accepted approval")
            self._revocations[revocation.revocation_id] = revocation

    def effective_approvals(
        self,
        *,
        account_ref: str,
        environment_ref: str,
        symbol: str,
        at: datetime,
    ) -> tuple[DemoExecutionApproval, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (
                        item
                        for item in self._approvals.values()
                        if item.account_ref == account_ref
                        and item.environment_ref == environment_ref
                        and item.symbol == symbol
                        and item.applies_at(at)
                        and not self.approval_is_revoked(
                            item.approval_id,
                            content_digest(item),
                        )
                    ),
                    key=lambda item: item.approval_id,
                )
            )

    def approval_is_revoked(self, approval_id: str, approval_digest: str) -> bool:
        return any(
            item.approval_id == approval_id and item.approval_digest == approval_digest
            for item in self._revocations.values()
        )

    def append_control_event(self, event: ExecutionControlEvent) -> None:
        with self._lock:
            previous = self._control_events[-1].state if self._control_events else None
            if event.previous_state is not previous:
                raise ValueError("control event does not continue the append-only state")
            self._control_events.append(event)

    def control_state(self) -> ExecutionControlState:
        with self._lock:
            return (
                self._control_events[-1].state
                if self._control_events
                else ExecutionControlState.DISABLED
            )

    def current_control_event(self) -> ExecutionControlEvent | None:
        with self._lock:
            return self._control_events[-1] if self._control_events else None

    def claim(
        self,
        intent: DemoOrderIntent,
        preflight: DemoExecutionPreflight,
        risk_revalidation: FreshRiskRevalidation,
        owner: str,
        claimed_at: datetime,
    ) -> DemoExecutionRecord:
        with self._lock:
            if (
                intent.execution_intent_id in self._records
                or intent.source_shadow_intent_digest in self._source_index
                or intent.client_trade_id in self._client_index
            ):
                raise DemoExecutionError(
                    DemoExecutionFailureCategory.DUPLICATE_EXECUTION_INTENT,
                    "execution identity or source shadow intent was already claimed",
                )
            record = DemoExecutionRecord(
                intent=intent,
                state=DemoExecutionState.CLAIMED,
                claim_owner=owner,
                preflight=preflight,
                risk_revalidation=risk_revalidation,
                events=(
                    DemoExecutionEvent(
                        sequence=1,
                        state=DemoExecutionState.CREATED,
                        occurred_at=intent.created_at,
                    ),
                    DemoExecutionEvent(
                        sequence=2,
                        state=DemoExecutionState.CLAIMED,
                        occurred_at=claimed_at,
                    ),
                ),
            )
            self._records[intent.execution_intent_id] = record
            self._source_index[intent.source_shadow_intent_digest] = intent.execution_intent_id
            self._client_index[intent.client_trade_id] = intent.execution_intent_id
            return record

    def claim_is_owned(self, execution_intent_id: str, owner: str) -> bool:
        with self._lock:
            record = self._records.get(execution_intent_id)
            return bool(
                record is not None
                and record.claim_owner == owner
                and record.state is DemoExecutionState.CLAIMED
            )

    def save(self, record: DemoExecutionRecord) -> None:
        with self._lock:
            current = self._records.get(record.intent.execution_intent_id)
            if current is None:
                raise ValueError("execution record has not been claimed")
            if record.intent != current.intent or record.claim_owner != current.claim_owner:
                raise ValueError("execution intent or claim owner cannot be changed")
            if len(record.events) != len(current.events) + 1 or (
                record.events[:-1] != current.events
            ):
                raise ValueError("execution record updates must append exactly one event")
            self._records[record.intent.execution_intent_id] = record

    def get(self, execution_intent_id: str) -> DemoExecutionRecord | None:
        return self._records.get(execution_intent_id)

    def get_by_source_digest(self, digest: str) -> DemoExecutionRecord | None:
        intent_id = self._source_index.get(digest)
        return None if intent_id is None else self._records[intent_id]

    def recover_incomplete(self, recovered_at: datetime) -> tuple[DemoExecutionRecord, ...]:
        """Never resume or redispatch a record after process restart."""
        recovered: list[DemoExecutionRecord] = []
        with self._lock:
            for current in tuple(self._records.values()):
                if current.state in {DemoExecutionState.CREATED, DemoExecutionState.CLAIMED}:
                    failure = DemoExecutionFailure(
                        code=DemoExecutionFailureCategory.PROCESS_RESTART,
                        sanitized_detail="pre-dispatch execution was abandoned after restart",
                    )
                    updated = _transition(
                        current,
                        DemoExecutionState.REJECTED,
                        recovered_at,
                        failure=failure,
                    )
                elif current.state in {
                    DemoExecutionState.DISPATCHING,
                    DemoExecutionState.SUBMITTED,
                }:
                    failure = DemoExecutionFailure(
                        code=DemoExecutionFailureCategory.DISPATCH_RESULT_UNKNOWN,
                        sanitized_detail="dispatch state is uncertain after process restart",
                    )
                    submission = current.submission or DemoSubmissionReceipt(
                        execution_intent_id=current.intent.execution_intent_id,
                        intent_digest=current.intent.intent_digest,
                        disposition=DemoSubmissionDisposition.UNKNOWN,
                        dispatch_started_at=current.events[-1].occurred_at,
                        dispatch_completed_at=recovered_at,
                        sanitized_detail="no broker response survived process restart",
                    )
                    updated = _transition(
                        current,
                        DemoExecutionState.UNKNOWN,
                        recovered_at,
                        failure=failure,
                        submission=submission,
                    )
                else:
                    continue
                self._records[current.intent.execution_intent_id] = updated
                recovered.append(updated)
        return tuple(recovered)


class SQLiteDemoExecutionRepository(InMemoryDemoExecutionRepository):
    """SQLite-backed approvals, controls, immutable intents, and appended revisions."""

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_environment_acceptance (
                acceptance_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_approval (
                approval_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_approval_revocation (
                revocation_id TEXT PRIMARY KEY, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_control_event (
                event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_intent (
                intent_id TEXT PRIMARY KEY, source_digest TEXT NOT NULL UNIQUE,
                client_trade_id TEXT NOT NULL UNIQUE, intent_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_record_revision (
                intent_id TEXT NOT NULL, revision INTEGER NOT NULL,
                record_json TEXT NOT NULL, PRIMARY KEY (intent_id, revision))"""
            )
        self._load()

    def close(self) -> None:
        self._connection.close()

    def add_environment_acceptance(
        self, acceptance: DemoExecutionEnvironmentAcceptance
    ) -> None:
        super().add_environment_acceptance(acceptance)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_environment_acceptance VALUES (?, ?)",
                    (acceptance.acceptance_id, acceptance.model_dump_json()),
                )
        except Exception:
            self._acceptances.pop(acceptance.acceptance_id, None)
            raise

    def add_approval(self, approval: DemoExecutionApproval) -> None:
        super().add_approval(approval)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_approval VALUES (?, ?)",
                    (approval.approval_id, approval.model_dump_json()),
                )
        except Exception:
            self._approvals.pop(approval.approval_id, None)
            raise

    def revoke_approval(self, revocation: DemoExecutionApprovalRevocation) -> None:
        super().revoke_approval(revocation)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_approval_revocation VALUES (?, ?)",
                    (revocation.revocation_id, revocation.model_dump_json()),
                )
        except Exception:
            self._revocations.pop(revocation.revocation_id, None)
            raise

    def append_control_event(self, event: ExecutionControlEvent) -> None:
        super().append_control_event(event)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_control_event VALUES (?, ?, ?)",
                    (event.event_id, event.occurred_at.isoformat(), event.model_dump_json()),
                )
        except Exception:
            self._control_events.pop()
            raise

    def claim(
        self,
        intent: DemoOrderIntent,
        preflight: DemoExecutionPreflight,
        risk_revalidation: FreshRiskRevalidation,
        owner: str,
        claimed_at: datetime,
    ) -> DemoExecutionRecord:
        record = super().claim(intent, preflight, risk_revalidation, owner, claimed_at)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_intent VALUES (?, ?, ?, ?)",
                    (
                        intent.execution_intent_id,
                        intent.source_shadow_intent_digest,
                        intent.client_trade_id,
                        intent.model_dump_json(),
                    ),
                )
                self._insert_revision(record)
        except Exception:
            self._records.pop(intent.execution_intent_id, None)
            self._source_index.pop(intent.source_shadow_intent_digest, None)
            self._client_index.pop(intent.client_trade_id, None)
            raise
        return record

    def save(self, record: DemoExecutionRecord) -> None:
        current = self._records.get(record.intent.execution_intent_id)
        super().save(record)
        try:
            with self._connection:
                self._insert_revision(record)
        except Exception:
            if current is not None:
                self._records[record.intent.execution_intent_id] = current
            raise

    def recover_incomplete(self, recovered_at: datetime) -> tuple[DemoExecutionRecord, ...]:
        previous = dict(self._records)
        recovered = super().recover_incomplete(recovered_at)
        try:
            with self._connection:
                for record in recovered:
                    self._insert_revision(record)
        except Exception:
            self._records = previous
            raise
        return recovered

    def _insert_revision(self, record: DemoExecutionRecord) -> None:
        self._connection.execute(
            "INSERT INTO m11_record_revision VALUES (?, ?, ?)",
            (
                record.intent.execution_intent_id,
                len(record.events),
                record.model_dump_json(),
            ),
        )

    def _load(self) -> None:
        for row in self._connection.execute(
            "SELECT record_json FROM m11_environment_acceptance"
        ):
            acceptance = DemoExecutionEnvironmentAcceptance.model_validate_json(row[0])
            self._acceptances[acceptance.acceptance_id] = acceptance
        for row in self._connection.execute("SELECT record_json FROM m11_approval"):
            approval = DemoExecutionApproval.model_validate_json(row[0])
            self._approvals[approval.approval_id] = approval
        for row in self._connection.execute(
            "SELECT record_json FROM m11_approval_revocation"
        ):
            revocation = DemoExecutionApprovalRevocation.model_validate_json(row[0])
            self._revocations[revocation.revocation_id] = revocation
        for row in self._connection.execute(
            "SELECT record_json FROM m11_control_event ORDER BY occurred_at, event_id"
        ):
            self._control_events.append(ExecutionControlEvent.model_validate_json(row[0]))
        for row in self._connection.execute(
            """SELECT r.record_json FROM m11_record_revision r
            JOIN (SELECT intent_id, MAX(revision) AS revision FROM m11_record_revision
                  GROUP BY intent_id) latest
            ON r.intent_id = latest.intent_id AND r.revision = latest.revision"""
        ):
            record = DemoExecutionRecord.model_validate_json(row[0])
            self._records[record.intent.execution_intent_id] = record
            self._source_index[record.intent.source_shadow_intent_digest] = (
                record.intent.execution_intent_id
            )
            self._client_index[record.intent.client_trade_id] = (
                record.intent.execution_intent_id
            )


def _transition(
    record: DemoExecutionRecord,
    state: DemoExecutionState,
    occurred_at: datetime,
    *,
    failure: DemoExecutionFailure | None = None,
    submission: DemoSubmissionReceipt | None = None,
) -> DemoExecutionRecord:
    return record.model_copy(
        update={
            "state": state,
            "submission": submission or record.submission,
            "events": record.events
            + (
                DemoExecutionEvent(
                    sequence=len(record.events) + 1,
                    state=state,
                    occurred_at=occurred_at,
                    failure=failure,
                ),
            ),
        }
    )
