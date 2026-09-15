"""Two-phase, explicitly invoked M11 real-DEMO acceptance coordinator."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ai_trading_team.execution.acceptance import validate_execution_authority
from ai_trading_team.execution.identifiers import execution_snapshot_id
from ai_trading_team.execution.preflight import validate_fresh_execution_observation
from ai_trading_team.execution.protocols import (
    DemoExecutionAdapter,
    DemoExecutionObservationSource,
    DemoExecutionRepository,
)
from ai_trading_team.execution.service import DemoExecutionService
from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import DemoExecutionState, ExecutionControlState
from ai_trading_team.schemas.execution import (
    DemoExecutionApproval,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPolicy,
    ExecutionControlEvent,
    QualifiedDemoExecutionCandidate,
)
from ai_trading_team.schemas.execution_acceptance import (
    RealDemoAcceptanceRecord,
    RealDemoAcceptanceStatus,
    RealDemoMutationApproval,
    RealDemoReadinessRecord,
)
from ai_trading_team.utils.time import utc_now


class RealDemoAcceptanceRepository(Protocol):
    def add_readiness(self, readiness: RealDemoReadinessRecord) -> None: ...

    def consume(
        self,
        readiness: RealDemoReadinessRecord,
        approval: RealDemoMutationApproval,
        control_event: ExecutionControlEvent,
        *,
        consumed_at: datetime,
    ) -> None: ...

    def save_result(self, record: RealDemoAcceptanceRecord) -> None: ...

    def is_consumed(self, readiness_generation_id: str) -> bool: ...


class RealDemoAcceptanceCoordinator:
    """Readiness is non-consuming; execution delegates once to the accepted M11 service."""

    readiness_checks = (
        "candidate_authority",
        "effective_human_approval",
        "execution_control_generation",
        "demo_environment",
        "fresh_terminal_observation",
        "zero_open_positions",
        "fresh_tick",
        "spread_and_drift",
        "symbol_capability",
    )

    def __init__(
        self,
        *,
        source: DemoExecutionObservationSource,
        adapter: DemoExecutionAdapter,
        execution_repository: DemoExecutionRepository,
        acceptance_repository: RealDemoAcceptanceRepository,
        execution_service: DemoExecutionService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._source = source
        self._adapter = adapter
        self._execution_repository = execution_repository
        self._acceptance_repository = acceptance_repository
        self._execution_service = execution_service
        self._clock = clock

    def readiness_only(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        policy: DemoExecutionPolicy,
        *,
        acceptance_run_id: str,
        readiness_generation_id: str,
        ttl_seconds: int = 300,
    ) -> RealDemoReadinessRecord:
        """Perform terminal reads and validation without claim, check, or submission."""
        if not 1 <= ttl_seconds <= 900:
            raise ValueError("readiness TTL must be between 1 and 900 seconds")
        created = self._now()
        control = self._require_enabled_control()
        approval = self._require_single_approval(candidate, acceptance, created)
        validate_execution_authority(
            candidate,
            acceptance,
            approval,
            policy,
            control_state=control.state,
            approval_revoked=self._execution_repository.approval_is_revoked(
                approval.approval_id, content_digest(approval)
            ),
            evaluated_at=created,
        )
        snapshot_id = execution_snapshot_id(candidate.decision.cycle_id, created)
        observation = self._source.capture(candidate.decision.cycle_id, snapshot_id)
        completed = self._now()
        preflight = validate_fresh_execution_observation(
            candidate,
            observation,
            acceptance,
            policy,
            started_at=created,
            completed_at=completed,
        )
        payload = {
            "acceptance_run_id": acceptance_run_id,
            "readiness_generation_id": readiness_generation_id,
            "readiness_created_at": created,
            "readiness_expires_at": created + timedelta(seconds=ttl_seconds),
            "candidate_id": candidate.candidate_id,
            "candidate_digest": content_digest(candidate),
            "candidate_generation_id": candidate.dependency_manifest.generation_id,
            "candidate_generation_digest": candidate.dependency_manifest_digest,
            "account_ref": acceptance.account_ref,
            "environment_ref": acceptance.environment_ref,
            "environment_acceptance_id": acceptance.acceptance_id,
            "environment_acceptance_digest": content_digest(acceptance),
            "policy_ref": policy.policy_ref,
            "policy_version": policy.policy_version,
            "policy_digest": content_digest(policy),
            "execution_control_event_id": control.event_id,
            "execution_control_event_digest": content_digest(control),
            "execution_control_state": control.state,
            "execution_snapshot_id": observation.snapshot.snapshot_id,
            "preflight_digest": content_digest(preflight),
            "checks": self.readiness_checks,
            "single_use": True,
        }
        readiness = RealDemoReadinessRecord.model_validate(
            {**payload, "readiness_digest": "sha256:" + "0" * 64}
        )
        readiness = readiness.model_copy(
            update={
                "readiness_digest": content_digest(
                    readiness.model_dump(mode="python", exclude={"readiness_digest"})
                )
            }
        )
        self._acceptance_repository.add_readiness(readiness)
        return readiness

    def execute_once(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        policy: DemoExecutionPolicy,
        readiness: RealDemoReadinessRecord,
        mutation_approval: RealDemoMutationApproval,
        *,
        claim_owner: str,
    ) -> RealDemoAcceptanceRecord:
        """Consume readiness once, then invoke the existing one-shot M11 state machine."""
        if self._acceptance_repository.is_consumed(readiness.readiness_generation_id):
            raise ValueError("readiness evidence was already consumed")
        consumed_at = self._now()
        control = self._require_enabled_control()
        self._acceptance_repository.consume(
            readiness,
            mutation_approval,
            control,
            consumed_at=consumed_at,
        )
        try:
            record = self._execution_service.execute(
                candidate,
                acceptance,
                policy,
                claim_owner=claim_owner,
            )
        except Exception:
            self._set_control(
                ExecutionControlState.HALTED,
                "one-shot real-DEMO execution failed after readiness consumption",
            )
            raise
        audit = self._adapter.get_vendor_boundary_audit(record.intent.execution_intent_id)
        status = _acceptance_status(record.state)
        result_payload = {
            "acceptance_record_id": deterministic_id(
                "real-demo-acceptance-record",
                {
                    "acceptance_run_id": readiness.acceptance_run_id,
                    "execution_intent_id": record.intent.execution_intent_id,
                },
            ),
            "acceptance_run_id": readiness.acceptance_run_id,
            "readiness_generation_id": readiness.readiness_generation_id,
            "readiness_digest": readiness.readiness_digest,
            "mutation_approval_id": mutation_approval.mutation_approval_id,
            "mutation_approval_digest": content_digest(mutation_approval),
            "candidate_id": candidate.candidate_id,
            "candidate_digest": content_digest(candidate),
            "account_ref": acceptance.account_ref,
            "environment_ref": acceptance.environment_ref,
            "symbol": candidate.decision.symbol,
            "side": record.intent.side,
            "policy_digest": content_digest(policy),
            "execution_control_event_id": control.event_id,
            "execution_control_event_digest": content_digest(control),
            "status": status,
            "submission_count": 1 if record.submission is not None else 0,
            "execution_record": record,
            "vendor_boundary_audit": audit,
            "sealed_at": self._now(),
        }
        result = RealDemoAcceptanceRecord.model_validate(
            {**result_payload, "record_digest": "sha256:" + "0" * 64}
        )
        result = result.model_copy(
            update={
                "record_digest": content_digest(
                    result.model_dump(mode="python", exclude={"record_digest"})
                )
            }
        )
        try:
            self._acceptance_repository.save_result(result)
        except Exception:
            self._set_control(
                ExecutionControlState.HALTED,
                "real-DEMO acceptance result persistence failed",
            )
            raise
        self._finish_control(record.state)
        return result

    def _require_single_approval(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        at: datetime,
    ) -> DemoExecutionApproval:
        approvals = self._execution_repository.effective_approvals(
            account_ref=acceptance.account_ref,
            environment_ref=acceptance.environment_ref,
            symbol=candidate.decision.symbol,
            at=at,
        )
        if len(approvals) != 1:
            raise ValueError("exactly one effective M11 human approval is required")
        return approvals[0]

    def _require_enabled_control(self) -> ExecutionControlEvent:
        event = self._execution_repository.current_control_event()
        if event is None or event.state is not ExecutionControlState.ENABLED:
            raise ValueError("execution control must have one explicit ENABLED generation")
        return event

    def _finish_control(self, state: DemoExecutionState) -> None:
        current = self._execution_repository.current_control_event()
        if current is None or current.state is not ExecutionControlState.ENABLED:
            return
        terminal = (
            ExecutionControlState.PAUSED
            if state in {DemoExecutionState.CONFIRMED, DemoExecutionState.REJECTED}
            else ExecutionControlState.HALTED
        )
        self._set_control(terminal, "one-shot real-DEMO acceptance run completed")

    def _set_control(self, terminal: ExecutionControlState, reason: str) -> None:
        current = self._execution_repository.current_control_event()
        if current is None or current.state is not ExecutionControlState.ENABLED:
            return
        now = self._now()
        self._execution_repository.append_control_event(
            ExecutionControlEvent(
                event_id=deterministic_id(
                    "real-demo-post-run-control",
                    {"previous_event": current.event_id, "state": terminal.value, "at": now},
                ),
                previous_state=current.state,
                state=terminal,
                operator_ref="m11-real-demo-acceptance-guard",
                occurred_at=now,
                reason=reason,
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("real-DEMO acceptance clock must be timezone-aware")
        return value.astimezone(UTC)


def _acceptance_status(state: DemoExecutionState) -> RealDemoAcceptanceStatus:
    if state is DemoExecutionState.CONFIRMED:
        return RealDemoAcceptanceStatus.REAL_DEMO_ACCEPTED
    if state is DemoExecutionState.REJECTED:
        return RealDemoAcceptanceStatus.REAL_DEMO_REJECTED
    return RealDemoAcceptanceStatus.REAL_DEMO_UNKNOWN
