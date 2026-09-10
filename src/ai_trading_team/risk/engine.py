"""Deterministic orchestration of M3 risk validation and sizing."""

from datetime import UTC, datetime

from ai_trading_team.config.settings import RiskConstitutionSettings
from ai_trading_team.risk.account import AccountRiskEvaluator
from ai_trading_team.risk.proposal import ProposalValidator
from ai_trading_team.risk.reasons import risk_reason
from ai_trading_team.risk.sizing import PositionSizer
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import RiskDecisionStatus, RiskReasonCode, RiskState
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision
from ai_trading_team.utils.logging import get_logger


class RiskEngine:
    """Produce an immutable risk decision without broker or execution access."""

    def __init__(self, settings: RiskConstitutionSettings) -> None:
        self._account = AccountRiskEvaluator(settings)
        self._proposal = ProposalValidator(settings)
        self._sizer = PositionSizer()
        self._logger = get_logger(__name__)

    def evaluate(
        self,
        proposal: TradeProposal,
        snapshot: MarketSnapshot,
        account_context: AccountRiskContext,
        evaluated_at: datetime,
    ) -> RiskDecision:
        """Evaluate identical explicit inputs identically, including reason order."""
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)

        proposal_result = self._proposal.validate(proposal, snapshot)
        account_result = self._account.evaluate(snapshot, account_context, evaluated_at)
        reasons = list(proposal_result.reasons)
        reasons.extend(account_result.reasons)
        if evaluated_at < snapshot.snapshot_completed_at or evaluated_at < proposal.timestamp:
            reasons.append(
                risk_reason(
                    RiskReasonCode.EVALUATION_TIMESTAMP_INVALID,
                    "evaluation timestamp predates an evaluated input",
                )
            )

        sizing = None
        if not reasons and proposal_result.stop_distance is not None:
            sizing_outcome = self._sizer.calculate(
                equity=account_result.metrics.current_equity,
                risk_percent=account_result.metrics.permitted_risk_percent,
                stop_distance=proposal_result.stop_distance,
                symbol_info=snapshot.symbol_info,
            )
            sizing = sizing_outcome.result
            reasons.extend(sizing_outcome.reasons)

        if account_result.state is RiskState.HALTED:
            status = RiskDecisionStatus.HALTED
        elif reasons:
            status = RiskDecisionStatus.REJECTED
        else:
            status = RiskDecisionStatus.APPROVED

        decision = RiskDecision(
            cycle_id=snapshot.cycle_id,
            snapshot_id=snapshot.snapshot_id,
            schema_version="1.0.0",
            timestamp=evaluated_at,
            proposal_id=proposal.proposal_id,
            account_ref=account_context.account_ref,
            symbol=snapshot.symbol,
            status=status,
            risk_state=account_result.state,
            reasons=tuple(reasons),
            account_metrics=account_result.metrics,
            position_sizing=sizing,
        )
        self._logger.info(
            "risk_evaluation_completed",
            extra={
                "cycle_id": decision.cycle_id,
                "snapshot_id": decision.snapshot_id,
                "proposal_id": decision.proposal_id,
                "account_ref": decision.account_ref,
                "symbol": decision.symbol,
                "status": decision.status.value,
                "risk_state": decision.risk_state.value,
                "reason_codes": [item.code.value for item in decision.reasons],
            },
        )
        return decision
