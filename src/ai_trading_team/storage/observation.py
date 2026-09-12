"""Durable M9 claims, baseline lifecycle, and sanitized research records."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from threading import RLock
from typing import Protocol

from ai_trading_team.observation.errors import ObservationRuntimeError
from ai_trading_team.schemas.enums import (
    DecisionClaimState,
    ObservationFailureCategory,
    RiskBaselineState,
)
from ai_trading_team.schemas.observation import (
    CompletedDecisionCandle,
    ContinuousDecisionRecord,
    DecisionCandleClaim,
    PendingShadowOutcome,
    RiskBaselineRecord,
)


class ObservationRepository(Protocol):
    def discover(self, candle: CompletedDecisionCandle) -> DecisionCandleClaim: ...

    def claim(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim: ...

    def bind_snapshot(
        self, decision_key: str, snapshot_id: str, *, at: datetime
    ) -> DecisionCandleClaim: ...

    def mark_processing(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim: ...

    def mark_terminal(
        self,
        decision_key: str,
        state: DecisionClaimState,
        *,
        at: datetime,
        failure_category: ObservationFailureCategory | None = None,
        detail: str | None = None,
    ) -> DecisionCandleClaim: ...

    def recover_incomplete(self, *, at: datetime) -> tuple[DecisionCandleClaim, ...]: ...

    def get_claim(self, decision_key: str) -> DecisionCandleClaim | None: ...

    def append_decision(self, record: ContinuousDecisionRecord) -> None: ...

    def get_decision(self, decision_key: str) -> ContinuousDecisionRecord | None: ...

    def append_baseline(self, record: RiskBaselineRecord) -> None: ...

    def active_baselines(
        self, account_ref: str, trading_day: date, *, at: datetime
    ) -> tuple[RiskBaselineRecord, ...]: ...

    def supersede_baseline(
        self, baseline_id: str, replacement: RiskBaselineRecord, *, at: datetime
    ) -> None: ...

    def invalidate_baseline(self, baseline_id: str, *, at: datetime, reason: str) -> None: ...

    def append_pending_outcome(self, record: PendingShadowOutcome) -> None: ...

    def update_outcome(self, record: PendingShadowOutcome) -> None: ...

    def get_outcome(self, tracking_id: str) -> PendingShadowOutcome | None: ...

    def pending_outcomes(self) -> tuple[PendingShadowOutcome, ...]: ...


class InMemoryObservationRepository:
    def __init__(self) -> None:
        self._claims: dict[str, DecisionCandleClaim] = {}
        self._snapshot_ids: set[str] = set()
        self._decisions: dict[str, ContinuousDecisionRecord] = {}
        self._baselines: dict[str, RiskBaselineRecord] = {}
        self._outcomes: dict[str, PendingShadowOutcome] = {}
        self._lock = RLock()

    def discover(self, candle: CompletedDecisionCandle) -> DecisionCandleClaim:
        with self._lock:
            existing = self._claims.get(candle.decision_key)
            if existing is not None:
                if existing.candle_digest != candle.candle_digest:
                    raise ObservationRuntimeError(
                        ObservationFailureCategory.SOURCE_CANDLE_REVISED,
                        "an existing decision candle was observed with revised content",
                    )
                return existing
            if any(item.cycle_id == candle.cycle_id for item in self._claims.values()):
                raise ValueError("cycle identity is already bound to another decision key")
            claim = DecisionCandleClaim(
                decision_key=candle.decision_key,
                cycle_id=candle.cycle_id,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                candle_open_at=candle.candle_open_at,
                candle_close_at=candle.candle_close_at,
                candle_digest=candle.candle_digest,
                state=DecisionClaimState.DISCOVERED,
                discovered_at=candle.observed_at,
                updated_at=candle.observed_at,
            )
            self._claims[candle.decision_key] = claim
            return claim

    def claim(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim:
        return self._transition(
            decision_key,
            DecisionClaimState.DISCOVERED,
            DecisionClaimState.CLAIMED,
            at,
        )

    def bind_snapshot(
        self, decision_key: str, snapshot_id: str, *, at: datetime
    ) -> DecisionCandleClaim:
        with self._lock:
            claim = self._require_state(decision_key, DecisionClaimState.CLAIMED)
            if snapshot_id in self._snapshot_ids:
                raise ObservationRuntimeError(
                    ObservationFailureCategory.SNAPSHOT_ID_CONFLICT,
                    "accepted snapshot identity is already bound to another decision",
                )
            updated = _validated_claim(
                claim,
                actual_snapshot_id=snapshot_id,
                updated_at=_utc(at),
            )
            self._claims[decision_key] = updated
            self._snapshot_ids.add(snapshot_id)
            return updated

    def mark_processing(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim:
        with self._lock:
            claim = self._require_state(decision_key, DecisionClaimState.CLAIMED)
            if claim.actual_snapshot_id is None:
                raise ValueError("actual accepted snapshot must be bound before processing")
        return self._transition(
            decision_key, DecisionClaimState.CLAIMED, DecisionClaimState.PROCESSING, at
        )

    def mark_terminal(
        self,
        decision_key: str,
        state: DecisionClaimState,
        *,
        at: datetime,
        failure_category: ObservationFailureCategory | None = None,
        detail: str | None = None,
    ) -> DecisionCandleClaim:
        if state not in {
            DecisionClaimState.COMPLETED,
            DecisionClaimState.FAILED,
            DecisionClaimState.MISSED,
            DecisionClaimState.ABANDONED,
        }:
            raise ValueError("target claim state is not terminal")
        with self._lock:
            claim = self._claims[decision_key]
            if claim.state not in {
                DecisionClaimState.DISCOVERED,
                DecisionClaimState.CLAIMED,
                DecisionClaimState.PROCESSING,
            }:
                raise ValueError("terminal claim cannot transition again")
            updated = _validated_claim(
                claim,
                state=state,
                updated_at=_utc(at),
                failure_category=failure_category,
                sanitized_detail=detail,
            )
            self._claims[decision_key] = updated
            return updated

    def recover_incomplete(self, *, at: datetime) -> tuple[DecisionCandleClaim, ...]:
        recovered = []
        for key, claim in tuple(self._claims.items()):
            if claim.state in {DecisionClaimState.CLAIMED, DecisionClaimState.PROCESSING}:
                recovered.append(
                    self.mark_terminal(
                        key,
                        DecisionClaimState.ABANDONED,
                        at=at,
                        failure_category=ObservationFailureCategory.PROCESS_RESTART,
                        detail="unfinished cycle was abandoned after process restart",
                    )
                )
        return tuple(recovered)

    def get_claim(self, decision_key: str) -> DecisionCandleClaim | None:
        return self._claims.get(decision_key)

    def append_decision(self, record: ContinuousDecisionRecord) -> None:
        with self._lock:
            if record.decision_key in self._decisions:
                raise ValueError("continuous decision record is append-only")
            self._decisions[record.decision_key] = record

    def get_decision(self, decision_key: str) -> ContinuousDecisionRecord | None:
        return self._decisions.get(decision_key)

    def append_baseline(self, record: RiskBaselineRecord) -> None:
        with self._lock:
            if record.baseline_id in self._baselines:
                raise ValueError("risk baseline identity already exists")
            self._baselines[record.baseline_id] = record

    def active_baselines(
        self, account_ref: str, trading_day: date, *, at: datetime
    ) -> tuple[RiskBaselineRecord, ...]:
        moment = _utc(at)
        return tuple(
            item
            for item in self._baselines.values()
            if item.state is RiskBaselineState.ACTIVE
            and item.account_ref == account_ref
            and item.utc_trading_day == trading_day
            and item.applies_at(moment)
        )

    def supersede_baseline(
        self, baseline_id: str, replacement: RiskBaselineRecord, *, at: datetime
    ) -> None:
        with self._lock:
            current = self._baselines[baseline_id]
            moment = _utc(at)
            if current.state is not RiskBaselineState.ACTIVE:
                raise ValueError("only an active baseline may be superseded")
            if replacement.state is not RiskBaselineState.ACTIVE:
                raise ValueError("replacement baseline must be active")
            if (
                replacement.account_ref != current.account_ref
                or replacement.utc_trading_day != current.utc_trading_day
                or replacement.effective_from != moment
            ):
                raise ValueError("replacement baseline identity or effective time is incompatible")
            if replacement.baseline_id in self._baselines:
                raise ValueError("replacement baseline identity already exists")
            old = _validated_baseline(
                current,
                state=RiskBaselineState.SUPERSEDED,
                effective_until=moment,
                superseded_by=replacement.baseline_id,
            )
            self._baselines[baseline_id] = old
            self._baselines[replacement.baseline_id] = replacement

    def invalidate_baseline(self, baseline_id: str, *, at: datetime, reason: str) -> None:
        with self._lock:
            current = self._baselines[baseline_id]
            if current.state is not RiskBaselineState.ACTIVE:
                raise ValueError("only an active baseline may be invalidated")
            self._baselines[baseline_id] = _validated_baseline(
                current,
                state=RiskBaselineState.INVALIDATED,
                effective_until=_utc(at),
                invalidation_reason=reason,
            )

    def append_pending_outcome(self, record: PendingShadowOutcome) -> None:
        with self._lock:
            if record.tracking_id in self._outcomes:
                raise ValueError("outcome tracking identity already exists")
            self._outcomes[record.tracking_id] = record

    def update_outcome(self, record: PendingShadowOutcome) -> None:
        with self._lock:
            current = self._outcomes[record.tracking_id]
            if current.state.value != "PENDING" or record.state.value == "PENDING":
                raise ValueError("outcome tracking permits exactly one terminal transition")
            if (
                current.decision_record_id != record.decision_record_id
                or current.decision_record_digest != record.decision_record_digest
                or current.shadow_intent != record.shadow_intent
            ):
                raise ValueError("terminal outcome cannot alter its frozen decision")
            self._outcomes[record.tracking_id] = record

    def get_outcome(self, tracking_id: str) -> PendingShadowOutcome | None:
        return self._outcomes.get(tracking_id)

    def pending_outcomes(self) -> tuple[PendingShadowOutcome, ...]:
        return tuple(
            item for item in self._outcomes.values() if item.state.value == "PENDING"
        )

    def _require_state(self, key: str, state: DecisionClaimState) -> DecisionCandleClaim:
        claim = self._claims[key]
        if claim.state is not state:
            raise ValueError(f"claim must be {state.value}")
        return claim

    def _transition(
        self,
        key: str,
        expected: DecisionClaimState,
        target: DecisionClaimState,
        at: datetime,
    ) -> DecisionCandleClaim:
        with self._lock:
            claim = self._require_state(key, expected)
            updated = _validated_claim(claim, state=target, updated_at=_utc(at))
            self._claims[key] = updated
            return updated


class SQLiteObservationRepository(InMemoryObservationRepository):
    """SQLite persistence using atomic transactions and validated canonical JSON records."""

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m9_claims (
                decision_key TEXT PRIMARY KEY, cycle_id TEXT NOT NULL UNIQUE,
                snapshot_id TEXT UNIQUE, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m9_decisions (
                decision_key TEXT PRIMARY KEY, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m9_risk_baselines (
                baseline_id TEXT PRIMARY KEY, account_ref TEXT NOT NULL,
                trading_day TEXT NOT NULL, state TEXT NOT NULL,
                effective_from TEXT NOT NULL, effective_until TEXT,
                record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m9_outcomes (
                tracking_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                record_json TEXT NOT NULL)"""
            )
        self._load()

    def close(self) -> None:
        self._connection.close()

    def discover(self, candle: CompletedDecisionCandle) -> DecisionCandleClaim:
        with self._lock:
            existing = self._claims.get(candle.decision_key)
            if existing is not None:
                return super().discover(candle)
            claim = super().discover(candle)
            try:
                with self._connection:
                    self._connection.execute(
                        "INSERT INTO m9_claims VALUES (?, ?, ?, ?)",
                        (claim.decision_key, claim.cycle_id, None, claim.model_dump_json()),
                    )
            except Exception:
                self._claims.pop(candle.decision_key, None)
                raise
            return claim

    def claim(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim:
        before = self._claims[decision_key]
        updated = super().claim(decision_key, at=at)
        try:
            return self._persist_claim(updated)
        except Exception:
            self._claims[decision_key] = before
            raise

    def bind_snapshot(
        self, decision_key: str, snapshot_id: str, *, at: datetime
    ) -> DecisionCandleClaim:
        before = self._claims[decision_key]
        updated = super().bind_snapshot(decision_key, snapshot_id, at=at)
        try:
            return self._persist_claim(updated)
        except Exception:
            self._claims[decision_key] = before
            self._snapshot_ids.discard(snapshot_id)
            raise

    def mark_processing(self, decision_key: str, *, at: datetime) -> DecisionCandleClaim:
        before = self._claims[decision_key]
        updated = super().mark_processing(decision_key, at=at)
        try:
            return self._persist_claim(updated)
        except Exception:
            self._claims[decision_key] = before
            raise

    def mark_terminal(
        self,
        decision_key: str,
        state: DecisionClaimState,
        *,
        at: datetime,
        failure_category: ObservationFailureCategory | None = None,
        detail: str | None = None,
    ) -> DecisionCandleClaim:
        before = self._claims[decision_key]
        updated = super().mark_terminal(
            decision_key,
            state,
            at=at,
            failure_category=failure_category,
            detail=detail,
        )
        try:
            return self._persist_claim(updated)
        except Exception:
            self._claims[decision_key] = before
            raise

    def append_decision(self, record: ContinuousDecisionRecord) -> None:
        super().append_decision(record)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m9_decisions VALUES (?, ?)",
                    (record.decision_key, record.model_dump_json()),
                )
        except Exception:
            self._decisions.pop(record.decision_key, None)
            raise

    def append_baseline(self, record: RiskBaselineRecord) -> None:
        super().append_baseline(record)
        try:
            self._insert_baseline(record)
        except Exception:
            self._baselines.pop(record.baseline_id, None)
            raise

    def supersede_baseline(
        self, baseline_id: str, replacement: RiskBaselineRecord, *, at: datetime
    ) -> None:
        before = self._baselines[baseline_id]
        super().supersede_baseline(baseline_id, replacement, at=at)
        try:
            with self._connection:
                self._update_baseline(self._baselines[baseline_id])
                self._insert_baseline(replacement, commit=False)
        except Exception:
            self._baselines[baseline_id] = before
            self._baselines.pop(replacement.baseline_id, None)
            raise

    def invalidate_baseline(self, baseline_id: str, *, at: datetime, reason: str) -> None:
        before = self._baselines[baseline_id]
        super().invalidate_baseline(baseline_id, at=at, reason=reason)
        try:
            with self._connection:
                self._update_baseline(self._baselines[baseline_id])
        except Exception:
            self._baselines[baseline_id] = before
            raise

    def append_pending_outcome(self, record: PendingShadowOutcome) -> None:
        super().append_pending_outcome(record)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m9_outcomes VALUES (?, ?, ?)",
                    (record.tracking_id, record.state.value, record.model_dump_json()),
                )
        except Exception:
            self._outcomes.pop(record.tracking_id, None)
            raise

    def update_outcome(self, record: PendingShadowOutcome) -> None:
        before = self._outcomes[record.tracking_id]
        super().update_outcome(record)
        try:
            with self._connection:
                self._connection.execute(
                    "UPDATE m9_outcomes SET state = ?, record_json = ? WHERE tracking_id = ?",
                    (record.state.value, record.model_dump_json(), record.tracking_id),
                )
        except Exception:
            self._outcomes[record.tracking_id] = before
            raise

    def _persist_claim(self, claim: DecisionCandleClaim) -> DecisionCandleClaim:
        with self._connection:
            self._connection.execute(
                "UPDATE m9_claims SET snapshot_id = ?, record_json = ? WHERE decision_key = ?",
                (claim.actual_snapshot_id, claim.model_dump_json(), claim.decision_key),
            )
        return claim

    def _insert_baseline(self, record: RiskBaselineRecord, *, commit: bool = True) -> None:
        operation = self._connection if commit else self._connection
        operation.execute(
            "INSERT INTO m9_risk_baselines VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.baseline_id,
                record.account_ref,
                record.utc_trading_day.isoformat(),
                record.state.value,
                record.effective_from.isoformat(),
                None if record.effective_until is None else record.effective_until.isoformat(),
                record.model_dump_json(),
            ),
        )
        if commit:
            self._connection.commit()

    def _update_baseline(self, record: RiskBaselineRecord) -> None:
        self._connection.execute(
            """UPDATE m9_risk_baselines SET state = ?, effective_until = ?, record_json = ?
            WHERE baseline_id = ?""",
            (
                record.state.value,
                None if record.effective_until is None else record.effective_until.isoformat(),
                record.model_dump_json(),
                record.baseline_id,
            ),
        )

    def _load(self) -> None:
        for row in self._connection.execute("SELECT record_json FROM m9_claims"):
            claim = DecisionCandleClaim.model_validate_json(row[0])
            self._claims[claim.decision_key] = claim
            if claim.actual_snapshot_id is not None:
                self._snapshot_ids.add(claim.actual_snapshot_id)
        for row in self._connection.execute("SELECT record_json FROM m9_decisions"):
            record = ContinuousDecisionRecord.model_validate_json(row[0])
            self._decisions[record.decision_key] = record
        for row in self._connection.execute("SELECT record_json FROM m9_risk_baselines"):
            baseline = RiskBaselineRecord.model_validate_json(row[0])
            self._baselines[baseline.baseline_id] = baseline
        for row in self._connection.execute("SELECT record_json FROM m9_outcomes"):
            outcome = PendingShadowOutcome.model_validate_json(row[0])
            self._outcomes[outcome.tracking_id] = outcome


def _validated_claim(claim: DecisionCandleClaim, **changes: object) -> DecisionCandleClaim:
    return DecisionCandleClaim.model_validate(claim.model_copy(update=changes).model_dump())


def _validated_baseline(record: RiskBaselineRecord, **changes: object) -> RiskBaselineRecord:
    return RiskBaselineRecord.model_validate(record.model_copy(update=changes).model_dump())


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("repository timestamp must be timezone-aware")
    return value.astimezone(UTC)
