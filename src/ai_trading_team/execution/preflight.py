"""Fresh price/risk preflight and the immediate M11 FinalDispatchGuard."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.execution.acceptance import validate_execution_authority
from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.execution.identifiers import (
    capability_definition_digest,
    symbol_definition_digest,
    verify_demo_order_intent,
)
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk.account import account_fingerprint
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    DemoExecutionFailureCategory,
    ExecutionControlState,
    MT5ConnectionState,
    SymbolTradeMode,
    TradeSide,
)
from ai_trading_team.schemas.execution import (
    DemoExecutionApproval,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionFailure,
    DemoExecutionPolicy,
    DemoExecutionPreflight,
    DemoExecutionRecord,
    DemoSymbolExecutionCapabilities,
    ExecutionSnapshotLink,
    FinalDispatchGuardResult,
    FinalDispatchObservation,
    FreshExecutionObservation,
    QualifiedDemoExecutionCandidate,
    exact_deviation_points,
)
from ai_trading_team.schemas.mt5 import MT5SymbolInfo, MT5Tick
from ai_trading_team.schemas.shadow import ShadowTradeIntent


def validate_fresh_execution_observation(
    candidate: QualifiedDemoExecutionCandidate,
    observation: FreshExecutionObservation,
    acceptance: DemoExecutionEnvironmentAcceptance,
    policy: DemoExecutionPolicy,
    *,
    started_at: datetime,
    completed_at: datetime,
) -> DemoExecutionPreflight:
    """Validate fresh typed facts without strategy logic or risk calculations."""
    started = _utc(started_at)
    completed = _utc(completed_at)
    snapshot = observation.snapshot
    intent = _shadow_intent(candidate)
    link = ExecutionSnapshotLink(
        analysis_snapshot_id=intent.snapshot_id,
        execution_snapshot_id=snapshot.snapshot_id,
    )
    if completed < started or completed - started > timedelta(
        seconds=policy.maximum_preflight_seconds
    ):
        raise _error(
            DemoExecutionFailureCategory.PREFLIGHT_EXPIRED,
            "execution preflight exceeded its deterministic time bound",
        )
    if completed - candidate.decision.recorded_at > timedelta(
        seconds=policy.maximum_decision_age_seconds
    ):
        raise _error(
            DemoExecutionFailureCategory.DECISION_EXPIRED,
            "qualified shadow decision is too old for execution",
        )
    if snapshot.cycle_id != intent.cycle_id or snapshot.symbol != intent.proposal.symbol:
        raise _error(
            DemoExecutionFailureCategory.SYMBOL_MISMATCH,
            "execution snapshot does not match the qualified decision trace",
        )
    account_ref = account_fingerprint(snapshot.account.account_id, snapshot.account.server)
    if (
        account_ref != acceptance.account_ref
        or observation.risk_context_evidence.context.account_ref != acceptance.account_ref
    ):
        raise _error(
            DemoExecutionFailureCategory.ACCOUNT_MISMATCH,
            "fresh execution account differs from accepted DEMO account",
        )
    if observation.environment_ref != acceptance.environment_ref:
        raise _error(
            DemoExecutionFailureCategory.ENVIRONMENT_MISMATCH,
            "fresh execution environment differs from acceptance",
        )
    if snapshot.account.trade_mode is not BrokerAccountMode.DEMO:
        raise _error(
            DemoExecutionFailureCategory.NON_DEMO_ACCOUNT,
            "fresh execution account is not a DEMO account",
        )
    if observation.account_positions:
        raise _error(
            DemoExecutionFailureCategory.OPEN_POSITION_CONFLICT,
            "M11 requires zero account positions before dispatch",
        )
    _validate_symbol_capabilities(
        snapshot.symbol_info,
        observation.capabilities,
        acceptance,
        policy,
    )
    reference = snapshot.tick.ask if intent.proposal.side is TradeSide.BUY else snapshot.tick.bid
    spread_ticks, drift_ticks = _validate_quote(
        snapshot.tick,
        reference,
        intent.hypothetical_entry,
        snapshot.symbol_info.trade_tick_size,
        policy,
        completed,
    )
    adverse = policy.maximum_adverse_slippage_ticks * snapshot.symbol_info.trade_tick_size
    risk_price = (
        reference + adverse
        if intent.proposal.side is TradeSide.BUY
        else reference - adverse
    )
    deviation = exact_deviation_points(
        policy.maximum_adverse_slippage_ticks,
        snapshot.symbol_info.trade_tick_size,
        snapshot.symbol_info.point,
    )
    return DemoExecutionPreflight(
        snapshot_link=link,
        started_at=started,
        completed_at=completed,
        reference_price=reference,
        risk_validation_price=risk_price,
        spread_ticks=spread_ticks,
        price_drift_ticks=drift_ticks,
        maximum_deviation_points=deviation,
        execution_mode=observation.capabilities.execution_mode,
        passed=True,
    )


class FinalDispatchGuard:
    """Recheck mutable execution facts after order_check and immediately before dispatch."""

    checks = (
        "claim_ownership",
        "intent_expiry",
        "human_approval",
        "execution_control",
        "demo_environment",
        "open_positions",
        "tick_freshness",
        "spread",
        "price_drift",
        "symbol_capability",
        "sealed_linkage",
    )

    def evaluate(
        self,
        record: DemoExecutionRecord,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        approval: DemoExecutionApproval,
        policy: DemoExecutionPolicy,
        observation: FinalDispatchObservation,
        *,
        claim_owned: bool,
        approval_revoked: bool,
        control_state: ExecutionControlState,
        evaluated_at: datetime,
    ) -> FinalDispatchGuardResult:
        now = _utc(evaluated_at)
        try:
            if not claim_owned:
                raise _error(
                    DemoExecutionFailureCategory.CLAIM_NOT_OWNED,
                    "execution claim is no longer uniquely owned",
                )
            if now >= record.intent.expires_at:
                raise _error(
                    DemoExecutionFailureCategory.INTENT_EXPIRED,
                    "sealed intent expired before dispatch",
                )
            validate_execution_authority(
                candidate,
                acceptance,
                approval,
                policy,
                control_state=control_state,
                approval_revoked=approval_revoked,
                evaluated_at=now,
            )
            self._validate_observation(record, acceptance, policy, observation, now)
            self._validate_linkage(record, candidate, acceptance, approval, policy)
        except DemoExecutionError as exc:
            return FinalDispatchGuardResult(
                execution_intent_id=record.intent.execution_intent_id,
                evaluated_at=now,
                passed=False,
                checks=self.checks,
                failure=DemoExecutionFailure(
                    code=exc.category,
                    sanitized_detail=exc.message,
                ),
            )
        return FinalDispatchGuardResult(
            execution_intent_id=record.intent.execution_intent_id,
            evaluated_at=now,
            passed=True,
            checks=self.checks,
        )

    @staticmethod
    def _validate_observation(
        record: DemoExecutionRecord,
        acceptance: DemoExecutionEnvironmentAcceptance,
        policy: DemoExecutionPolicy,
        observation: FinalDispatchObservation,
        now: datetime,
    ) -> None:
        intent = record.intent
        if observation.account.trade_mode is not BrokerAccountMode.DEMO:
            raise _error(
                DemoExecutionFailureCategory.NON_DEMO_ACCOUNT,
                "final dispatch account is not DEMO",
            )
        if (
            observation.account_ref != intent.account_ref
            or observation.account_ref != acceptance.account_ref
        ):
            raise _error(
                DemoExecutionFailureCategory.ACCOUNT_MISMATCH,
                "final dispatch account differs from the sealed intent",
            )
        if (
            observation.environment_ref != intent.environment_ref
            or observation.environment_ref != acceptance.environment_ref
        ):
            raise _error(
                DemoExecutionFailureCategory.ENVIRONMENT_MISMATCH,
                "final dispatch environment differs from the sealed intent",
            )
        if observation.positions:
            raise _error(
                DemoExecutionFailureCategory.OPEN_POSITION_CONFLICT,
                "a conflicting position appeared before dispatch",
            )
        if observation.health.connection_state is not MT5ConnectionState.CONNECTED or (
            not observation.health.authenticated
            or observation.health.trade_api_disabled is not False
        ):
            raise _error(
                DemoExecutionFailureCategory.ENVIRONMENT_MISMATCH,
                "terminal is not connected and enabled for accepted DEMO execution",
            )
        if observation.tick.symbol != intent.symbol:
            raise _error(
                DemoExecutionFailureCategory.SYMBOL_MISMATCH,
                "final tick symbol differs from the sealed intent",
            )
        reference = observation.tick.ask if intent.side is TradeSide.BUY else observation.tick.bid
        _validate_quote(
            observation.tick,
            reference,
            intent.reference_price,
            observation.symbol_info.trade_tick_size,
            policy,
            now,
        )
        _validate_symbol_capabilities(
            observation.symbol_info,
            observation.capabilities,
            acceptance,
            policy,
        )

    @staticmethod
    def _validate_linkage(
        record: DemoExecutionRecord,
        candidate: QualifiedDemoExecutionCandidate,
        acceptance: DemoExecutionEnvironmentAcceptance,
        approval: DemoExecutionApproval,
        policy: DemoExecutionPolicy,
    ) -> None:
        intent = record.intent
        shadow_intent = _shadow_intent(candidate)
        if not verify_demo_order_intent(intent):
            raise _error(
                DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
                "sealed intent digest changed",
            )
        checks = (
            intent.source_decision_record_digest == content_digest(candidate.decision),
            intent.source_shadow_intent_digest == content_digest(shadow_intent),
            intent.analysis_risk_decision_digest == content_digest(shadow_intent.risk_decision),
            intent.qualification_status_digest == content_digest(candidate.qualification_status),
            intent.generation_digest == content_digest(candidate.dependency_manifest),
            intent.environment_acceptance_digest == content_digest(acceptance),
            intent.approval_digest == content_digest(approval),
            intent.execution_policy_digest == content_digest(policy),
            record.risk_revalidation is not None,
            record.risk_revalidation is not None
            and intent.revalidation_risk_decision_digest
            == content_digest(record.risk_revalidation.risk_decision),
        )
        if not all(checks):
            raise _error(
                DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
                "intent, RiskDecision, or qualification linkage changed",
            )


def _validate_symbol_capabilities(
    symbol_info: object,
    capabilities: object,
    acceptance: DemoExecutionEnvironmentAcceptance,
    policy: DemoExecutionPolicy,
) -> None:
    if not isinstance(symbol_info, MT5SymbolInfo) or not isinstance(
        capabilities, DemoSymbolExecutionCapabilities
    ):
        raise _error(
            DemoExecutionFailureCategory.BROKER_METADATA_CHANGED,
            "invalid typed broker capability observation",
        )
    if capabilities.symbol_info_digest != symbol_definition_digest(symbol_info):
        raise _error(
            DemoExecutionFailureCategory.BROKER_METADATA_CHANGED,
            "execution capabilities do not bind current symbol metadata",
        )
    if capability_definition_digest(capabilities) != acceptance.symbol_capability_digest:
        raise _error(
            DemoExecutionFailureCategory.BROKER_METADATA_CHANGED,
            "current execution capabilities differ from environment acceptance",
        )
    if capabilities.execution_mode not in policy.supported_execution_modes:
        raise _error(
            DemoExecutionFailureCategory.UNSUPPORTED_EXECUTION_MODE,
            "symbol execution mode is not accepted by policy",
        )
    if policy.filling_mode not in capabilities.filling_modes:
        raise _error(
            DemoExecutionFailureCategory.UNSUPPORTED_FILLING_MODE,
            "configured filling mode is unavailable",
        )
    if not (
        capabilities.market_order_allowed
        and capabilities.stop_loss_allowed
        and capabilities.take_profit_allowed
    ):
        raise _error(
            DemoExecutionFailureCategory.PROTECTION_UNSUPPORTED,
            "symbol cannot accept the single protected market-order scope",
        )
    if (
        not symbol_info.selected
        or not symbol_info.visible
        or symbol_info.trading_mode
        in {SymbolTradeMode.DISABLED, SymbolTradeMode.CLOSE_ONLY}
    ):
        raise _error(
            DemoExecutionFailureCategory.UNSUPPORTED_EXECUTION_MODE,
            "symbol is unavailable, unselected, or not open-capable",
        )


def _validate_quote(
    tick: object,
    reference: Decimal,
    comparison_price: Decimal,
    tick_size: Decimal,
    policy: DemoExecutionPolicy,
    now: datetime,
) -> tuple[Decimal, Decimal]:
    if not isinstance(tick, MT5Tick) or tick_size <= 0:
        raise _error(
            DemoExecutionFailureCategory.BROKER_METADATA_CHANGED,
            "tick or tick-size metadata is invalid",
        )
    if tick.source_time > now or now - tick.source_time > timedelta(
        seconds=policy.maximum_tick_age_seconds
    ):
        raise _error(
            DemoExecutionFailureCategory.STALE_EXECUTION_TICK,
            "latest execution tick is future-dated or stale",
        )
    spread_ticks = tick.spread / tick_size
    if spread_ticks > policy.maximum_spread_ticks:
        raise _error(
            DemoExecutionFailureCategory.SPREAD_LIMIT_EXCEEDED,
            "execution spread exceeds the reviewed tick limit",
        )
    drift_ticks = abs(reference - comparison_price) / tick_size
    if drift_ticks > policy.maximum_price_drift_ticks:
        raise _error(
            DemoExecutionFailureCategory.PRICE_DRIFT_EXCEEDED,
            "execution price drift exceeds the reviewed tick limit",
        )
    return spread_ticks, drift_ticks


def _shadow_intent(candidate: QualifiedDemoExecutionCandidate) -> ShadowTradeIntent:
    shadow = candidate.decision.shadow_record
    if shadow is None or shadow.shadow_trade_intent is None:
        raise _error(
            DemoExecutionFailureCategory.QUALIFICATION_INELIGIBLE,
            "qualified decision has no approved shadow intent",
        )
    return shadow.shadow_trade_intent


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error(DemoExecutionFailureCategory.UNKNOWN, "execution time must be aware")
    return value.astimezone(UTC)


def _error(category: DemoExecutionFailureCategory, message: str) -> DemoExecutionError:
    return DemoExecutionError(category, message)
