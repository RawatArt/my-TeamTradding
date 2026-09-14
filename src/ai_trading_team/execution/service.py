"""One-shot, exactly-once M11 DEMO execution coordinator."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ai_trading_team.execution.acceptance import validate_execution_authority
from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.execution.identifiers import (
    client_trade_id,
    execution_intent_id,
    execution_snapshot_id,
    revalidation_proposal_id,
    seal_demo_order_intent,
)
from ai_trading_team.execution.preflight import (
    FinalDispatchGuard,
    validate_fresh_execution_observation,
)
from ai_trading_team.execution.protocols import (
    DemoExecutionAdapter,
    DemoExecutionObservationSource,
    DemoExecutionRepository,
)
from ai_trading_team.execution.reconciliation import reconcile_broker_evidence
from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk.engine import RiskEngine
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    DemoExecutionState,
    DemoReconciliationStatus,
    DemoSubmissionDisposition,
    ExecutionControlState,
    RiskDecisionStatus,
)
from ai_trading_team.schemas.execution import (
    DemoExecutionApproval,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionEvent,
    DemoExecutionFailure,
    DemoExecutionPolicy,
    DemoExecutionRecord,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    ExecutionControlEvent,
    FreshRiskRevalidation,
    QualifiedDemoExecutionCandidate,
)
from ai_trading_team.schemas.shadow import ShadowTradeIntent
from ai_trading_team.utils.logging import get_logger
from ai_trading_team.utils.time import utc_now


class DemoExecutionService:
    """Convert one qualified SHADOW intent into at most one protected DEMO submission."""

    def __init__(
        self,
        *,
        source: DemoExecutionObservationSource,
        adapter: DemoExecutionAdapter,
        repository: DemoExecutionRepository,
        risk_engine: RiskEngine,
        risk_engine_version: str,
        risk_policy_digest: str,
        clock: Callable[[], datetime] = utc_now,
        final_guard: FinalDispatchGuard | None = None,
    ) -> None:
        self._source = source
        self._adapter = adapter
        self._repository = repository
        self._risk_engine = risk_engine
        self._risk_engine_version = risk_engine_version
        self._risk_policy_digest = risk_policy_digest
        self._clock = clock
        self._guard = final_guard or FinalDispatchGuard()
        self._logger = get_logger(__name__)

    def execute(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        policy: DemoExecutionPolicy,
        *,
        claim_owner: str,
    ) -> DemoExecutionRecord:
        """Run the bounded CLAIMED -> check -> guard -> one-send workflow."""
        started = self._now()
        approval = self._require_single_approval(candidate, acceptance, started)
        self._validate_authority(candidate, acceptance, approval, policy, started)
        self._validate_risk_generation(candidate)

        snapshot_id = execution_snapshot_id(candidate.decision.cycle_id, started)
        observation = self._source.capture(candidate.decision.cycle_id, snapshot_id)
        preflight_completed = self._now()
        preflight = validate_fresh_execution_observation(
            candidate,
            observation,
            acceptance,
            policy,
            started_at=started,
            completed_at=preflight_completed,
        )
        revalidation = self._fresh_risk_revalidation(candidate, observation, preflight)
        intent = self._seal_intent(
            candidate,
            acceptance,
            approval,
            policy,
            preflight,
            revalidation,
            created_at=self._now(),
        )
        record = self._repository.claim(
            intent,
            preflight,
            revalidation,
            claim_owner,
            self._now(),
        )

        try:
            order_check = self._adapter.order_check(intent)
        except Exception as exc:
            return self._reject_before_dispatch(
                record,
                DemoExecutionFailureCategory.ADAPTER_FAILURE,
                "broker pre-dispatch check failed safely",
                self._now(),
                cause=exc,
            )
        if not order_check.accepted:
            return self._reject_before_dispatch(
                record,
                DemoExecutionFailureCategory.ORDER_CHECK_REJECTED,
                "broker pre-dispatch check rejected the sealed request",
                self._now(),
                order_check=order_check,
            )

        try:
            final_observation = self._adapter.observe_final_dispatch(intent)
        except Exception as exc:
            return self._reject_before_dispatch(
                record,
                DemoExecutionFailureCategory.ADAPTER_FAILURE,
                "final read-only dispatch observation failed",
                self._now(),
                order_check=order_check,
                cause=exc,
            )
        guard_time = self._now()
        guard = self._guard.evaluate(
            record,
            candidate,
            acceptance,
            approval,
            policy,
            final_observation,
            claim_owned=self._repository.claim_is_owned(
                intent.execution_intent_id,
                claim_owner,
            ),
            approval_revoked=self._repository.approval_is_revoked(
                approval.approval_id,
                content_digest(approval),
            ),
            control_state=self._repository.control_state(),
            evaluated_at=guard_time,
        )
        if not guard.passed:
            assert guard.failure is not None
            return self._reject_before_dispatch(
                record,
                guard.failure.code,
                guard.failure.sanitized_detail,
                guard_time,
                order_check=order_check,
                final_guard=guard,
            )

        dispatching = _advance(
            record,
            DemoExecutionState.DISPATCHING,
            guard_time,
            order_check=order_check,
            final_guard=guard,
        )
        self._repository.save(dispatching)
        try:
            receipt = self._adapter.submit_demo_market_intent(intent)
        except Exception as exc:
            now = self._now()
            receipt = DemoSubmissionReceipt(
                execution_intent_id=intent.execution_intent_id,
                intent_digest=intent.intent_digest,
                disposition=DemoSubmissionDisposition.UNKNOWN,
                dispatch_started_at=guard_time,
                dispatch_completed_at=now,
                sanitized_detail="broker dispatch result is unknown",
            )
            unknown = _advance(
                dispatching,
                DemoExecutionState.UNKNOWN,
                now,
                failure=_failure(
                    DemoExecutionFailureCategory.DISPATCH_RESULT_UNKNOWN,
                    "broker dispatch may have occurred; reconciliation only",
                ),
                submission=receipt,
            )
            self._repository.save(unknown)
            self._halt(now, "unknown broker dispatch result")
            self._logger.error(
                "demo_dispatch_unknown",
                extra={"execution_intent_id": intent.execution_intent_id},
            )
            del exc
            return unknown

        if receipt.disposition is DemoSubmissionDisposition.REJECTED:
            rejected = _advance(
                dispatching,
                DemoExecutionState.REJECTED,
                receipt.dispatch_completed_at,
                failure=_failure(
                    DemoExecutionFailureCategory.BROKER_REJECTED,
                    "broker definitively rejected the protected DEMO request",
                ),
                submission=receipt,
            )
            self._repository.save(rejected)
            return rejected
        if receipt.disposition is DemoSubmissionDisposition.UNKNOWN:
            unknown = _advance(
                dispatching,
                DemoExecutionState.UNKNOWN,
                receipt.dispatch_completed_at,
                failure=_failure(
                    DemoExecutionFailureCategory.DISPATCH_RESULT_UNKNOWN,
                    "broker dispatch result is unknown; reconciliation only",
                ),
                submission=receipt,
            )
            self._repository.save(unknown)
            self._halt(receipt.dispatch_completed_at, "unknown broker dispatch result")
            return unknown

        submitted = _advance(
            dispatching,
            DemoExecutionState.SUBMITTED,
            receipt.dispatch_completed_at,
            submission=receipt,
        )
        self._repository.save(submitted)
        return self._reconcile_record(submitted)

    def reconcile_unknown(self, execution_intent_id: str) -> DemoExecutionRecord:
        """Reconcile an uncertain submission without any path back to dispatch."""
        record = self._repository.get(execution_intent_id)
        if record is None or record.state is not DemoExecutionState.UNKNOWN:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.RECONCILIATION_FAILED,
                "only an existing UNKNOWN execution may be reconciled",
            )
        return self._reconcile_record(record)

    def _reconcile_record(self, record: DemoExecutionRecord) -> DemoExecutionRecord:
        receipt = record.submission
        if receipt is None:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.RECONCILIATION_FAILED,
                "post-dispatch record has no normalized submission receipt",
            )
        try:
            evidence = self._adapter.find_broker_evidence(record.intent, receipt)
        except Exception:
            if record.state is DemoExecutionState.SUBMITTED:
                unknown = _advance(
                    record,
                    DemoExecutionState.UNKNOWN,
                    self._now(),
                    failure=_failure(
                        DemoExecutionFailureCategory.RECONCILIATION_TIMEOUT,
                        "broker reconciliation failed; no resubmission is permitted",
                    ),
                )
                self._repository.save(unknown)
                self._halt(self._now(), "broker reconciliation failed")
                return unknown
            return record
        reconciliation = reconcile_broker_evidence(
            record.intent,
            receipt,
            evidence,
            reconciled_at=self._now(),
        )
        if reconciliation.status is DemoReconciliationStatus.CONFIRMED:
            confirmed = _advance(
                record,
                DemoExecutionState.CONFIRMED,
                reconciliation.reconciled_at,
                reconciliation=reconciliation,
            )
            self._repository.save(confirmed)
            return confirmed
        if reconciliation.status is DemoReconciliationStatus.NOT_FOUND:
            if record.state is DemoExecutionState.UNKNOWN:
                return record
            unknown = _advance(
                record,
                DemoExecutionState.UNKNOWN,
                reconciliation.reconciled_at,
                failure=reconciliation.failure,
                reconciliation=reconciliation,
            )
            self._repository.save(unknown)
            self._halt(reconciliation.reconciled_at, "broker evidence remains inconclusive")
            return unknown
        failed = _advance(
            record,
            DemoExecutionState.RECONCILIATION_FAILED,
            reconciliation.reconciled_at,
            failure=reconciliation.failure,
            reconciliation=reconciliation,
        )
        self._repository.save(failed)
        self._halt(reconciliation.reconciled_at, "broker reconciliation mismatch")
        return failed

    def _fresh_risk_revalidation(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        observation: object,
        preflight: object,
    ) -> FreshRiskRevalidation:
        from ai_trading_team.schemas.execution import (
            DemoExecutionPreflight,
            FreshExecutionObservation,
        )

        if not isinstance(observation, FreshExecutionObservation) or not isinstance(
            preflight, DemoExecutionPreflight
        ):
            raise TypeError("typed fresh execution inputs are required")
        shadow_intent = _shadow_intent(candidate)
        source = shadow_intent.proposal
        proposal = TradeProposal(
            cycle_id=observation.snapshot.cycle_id,
            snapshot_id=observation.snapshot.snapshot_id,
            timestamp=observation.snapshot.snapshot_completed_at,
            proposal_id=revalidation_proposal_id(
                source.proposal_id,
                observation.snapshot.snapshot_id,
            ),
            symbol=source.symbol,
            side=source.side,
            entry=preflight.risk_validation_price,
            stop_loss=source.stop_loss,
            take_profit=source.take_profit,
            rationale="Trusted pre-send revalidation of the immutable SHADOW proposal",
        )
        decision = self._risk_engine.evaluate(
            proposal,
            observation.snapshot,
            observation.risk_context_evidence.context,
            preflight.completed_at,
        )
        if decision.status is RiskDecisionStatus.HALTED:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.RISK_HALTED,
                "fresh deterministic Risk evaluation halted execution",
            )
        if decision.status is not RiskDecisionStatus.APPROVED or decision.position_sizing is None:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.RISK_REJECTED,
                "fresh deterministic Risk evaluation rejected execution",
            )
        if decision.position_sizing.selected_volume != shadow_intent.selected_volume:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.FRESH_VOLUME_MISMATCH,
                "fresh M3 volume differs from the immutable SHADOW-approved volume",
            )
        return FreshRiskRevalidation(
            snapshot_link=preflight.snapshot_link,
            original_proposal_id=source.proposal_id,
            original_proposal_digest=content_digest(source),
            original_risk_decision_digest=content_digest(shadow_intent.risk_decision),
            revalidation_proposal=proposal,
            revalidation_proposal_digest=content_digest(proposal),
            risk_decision=decision,
            risk_decision_digest=content_digest(decision),
            evaluated_at=preflight.completed_at,
        )

    def _seal_intent(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        approval: DemoExecutionApproval,
        policy: DemoExecutionPolicy,
        preflight: object,
        revalidation: FreshRiskRevalidation,
        *,
        created_at: datetime,
    ) -> DemoOrderIntent:
        from ai_trading_team.schemas.execution import DemoExecutionPreflight

        if not isinstance(preflight, DemoExecutionPreflight):
            raise TypeError("typed preflight is required")
        shadow_intent = _shadow_intent(candidate)
        proposal = shadow_intent.proposal
        fresh_sizing = revalidation.risk_decision.position_sizing
        if fresh_sizing is None or fresh_sizing.selected_volume is None:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.RISK_REJECTED,
                "fresh Risk decision has no approved volume",
            )
        source_digest = content_digest(shadow_intent)
        policy_digest = content_digest(policy)
        intent_id = execution_intent_id(
            source_digest,
            acceptance.environment_ref,
            policy_digest,
        )
        client_id = client_trade_id(intent_id)
        return seal_demo_order_intent(
            {
                "execution_intent_id": intent_id,
                "client_trade_id": client_id,
                "cycle_id": candidate.decision.cycle_id,
                "snapshot_link": preflight.snapshot_link,
                "account_ref": acceptance.account_ref,
                "environment_ref": acceptance.environment_ref,
                "symbol": candidate.decision.symbol,
                "side": proposal.side,
                "volume": fresh_sizing.selected_volume,
                "reference_price": preflight.reference_price,
                "risk_validation_price": preflight.risk_validation_price,
                "stop_loss": proposal.stop_loss,
                "take_profit": proposal.take_profit,
                "maximum_deviation_points": preflight.maximum_deviation_points,
                "execution_mode": preflight.execution_mode,
                "filling_mode": policy.filling_mode,
                "magic": policy.magic,
                "comment": f"{policy.comment_prefix}:{client_id[-16:]}",
                "source_decision_record_digest": content_digest(candidate.decision),
                "source_shadow_intent_digest": source_digest,
                "analysis_proposal_id": proposal.proposal_id,
                "analysis_proposal_digest": content_digest(proposal),
                "analysis_risk_decision_digest": content_digest(shadow_intent.risk_decision),
                "revalidation_proposal_id": revalidation.revalidation_proposal.proposal_id,
                "revalidation_proposal_digest": content_digest(
                    revalidation.revalidation_proposal
                ),
                "revalidation_risk_decision_digest": content_digest(
                    revalidation.risk_decision
                ),
                "qualification_run_id": candidate.qualification_status.qualification_run_id,
                "qualification_status_digest": content_digest(candidate.qualification_status),
                "generation_id": candidate.dependency_manifest.generation_id,
                "generation_digest": content_digest(candidate.dependency_manifest),
                "environment_acceptance_id": acceptance.acceptance_id,
                "environment_acceptance_digest": content_digest(acceptance),
                "approval_id": approval.approval_id,
                "approval_digest": content_digest(approval),
                "execution_policy_digest": policy_digest,
                "created_at": created_at,
                "expires_at": created_at + timedelta(seconds=policy.intent_ttl_seconds),
            }
        )

    def _require_single_approval(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        at: datetime,
    ) -> DemoExecutionApproval:
        approvals = self._repository.effective_approvals(
            account_ref=acceptance.account_ref,
            environment_ref=acceptance.environment_ref,
            symbol=candidate.decision.symbol,
            at=at,
        )
        if len(approvals) != 1:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.APPROVAL_MISSING,
                "exactly one compatible effective human DEMO approval is required",
            )
        return approvals[0]

    def _validate_authority(
        self,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        approval: DemoExecutionApproval,
        policy: DemoExecutionPolicy,
        at: datetime,
    ) -> None:
        validate_execution_authority(
            candidate,
            acceptance,
            approval,
            policy,
            control_state=self._repository.control_state(),
            approval_revoked=self._repository.approval_is_revoked(
                approval.approval_id,
                content_digest(approval),
            ),
            evaluated_at=at,
        )

    def _validate_risk_generation(self, candidate: QualifiedDemoExecutionCandidate) -> None:
        manifest = candidate.dependency_manifest
        if (
            manifest.risk_engine_version != self._risk_engine_version
            or manifest.risk_policy_digest != self._risk_policy_digest
        ):
            raise DemoExecutionError(
                DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
                "current M3 Risk generation differs from qualified evidence",
            )

    def _reject_before_dispatch(
        self,
        record: DemoExecutionRecord,
        category: DemoExecutionFailureCategory,
        detail: str,
        at: datetime,
        *,
        order_check: object | None = None,
        final_guard: object | None = None,
        cause: Exception | None = None,
    ) -> DemoExecutionRecord:
        from ai_trading_team.schemas.execution import DemoOrderCheckResult, FinalDispatchGuardResult

        updated = _advance(
            record,
            DemoExecutionState.REJECTED,
            at,
            failure=_failure(category, detail),
            order_check=order_check if isinstance(order_check, DemoOrderCheckResult) else None,
            final_guard=final_guard if isinstance(final_guard, FinalDispatchGuardResult) else None,
        )
        self._repository.save(updated)
        del cause
        return updated

    def _halt(self, at: datetime, reason: str) -> None:
        previous = self._repository.control_state()
        if previous is ExecutionControlState.HALTED:
            return
        event = ExecutionControlEvent(
            event_id=deterministic_id(
                "execution-control",
                {"previous": previous.value, "state": "HALTED", "at": at, "reason": reason},
            ),
            previous_state=previous,
            state=ExecutionControlState.HALTED,
            operator_ref="m11-safety-guard",
            occurred_at=at,
            reason=reason,
        )
        self._repository.append_control_event(event)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise DemoExecutionError(
                DemoExecutionFailureCategory.UNKNOWN,
                "execution clock must be timezone-aware",
            )
        return value.astimezone(UTC)


def _advance(
    record: DemoExecutionRecord,
    state: DemoExecutionState,
    at: datetime,
    *,
    failure: DemoExecutionFailure | None = None,
    order_check: object | None = None,
    final_guard: object | None = None,
    submission: DemoSubmissionReceipt | None = None,
    reconciliation: object | None = None,
) -> DemoExecutionRecord:
    from ai_trading_team.schemas.execution import (
        DemoOrderCheckResult,
        DemoReconciliationRecord,
        FinalDispatchGuardResult,
    )

    payload = record.model_dump(mode="python")
    payload.update(
        state=state,
        order_check=(
            order_check if isinstance(order_check, DemoOrderCheckResult) else record.order_check
        ),
        final_guard=(
            final_guard
            if isinstance(final_guard, FinalDispatchGuardResult)
            else record.final_guard
        ),
        submission=submission or record.submission,
        reconciliation=(
            reconciliation
            if isinstance(reconciliation, DemoReconciliationRecord)
            else record.reconciliation
        ),
        events=record.events
        + (
            DemoExecutionEvent(
                sequence=len(record.events) + 1,
                state=state,
                occurred_at=at,
                failure=failure,
            ),
        ),
    )
    return DemoExecutionRecord.model_validate(payload)


def _shadow_intent(candidate: QualifiedDemoExecutionCandidate) -> ShadowTradeIntent:
    record = candidate.decision.shadow_record
    if record is None or record.shadow_trade_intent is None:
        raise DemoExecutionError(
            DemoExecutionFailureCategory.QUALIFICATION_INELIGIBLE,
            "qualified decision has no approved shadow intent",
        )
    return record.shadow_trade_intent


def _failure(
    category: DemoExecutionFailureCategory,
    detail: str,
) -> DemoExecutionFailure:
    return DemoExecutionFailure(code=category, sanitized_detail=detail)
