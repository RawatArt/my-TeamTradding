"""Stateless account and portfolio risk calculations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from ai_trading_team.config.settings import RiskConstitutionSettings
from ai_trading_team.risk.reasons import risk_reason
from ai_trading_team.schemas.common import AccountReference
from ai_trading_team.schemas.enums import RiskReasonCode, RiskState
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import AccountRiskContext, AccountRiskMetrics, RiskReason

_ONE_HUNDRED = Decimal("100")


def account_fingerprint(account_id: int, server: str) -> AccountReference:
    """Derive a stable non-secret account reference without retaining raw inputs."""
    material = f"ai-trading-team:account:v1\0{server.casefold()}\0{account_id}".encode()
    return f"acct-v1:{sha256(material).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AccountRiskAssessment:
    """Internal result from deterministic account guard evaluation."""

    state: RiskState
    metrics: AccountRiskMetrics
    reasons: tuple[RiskReason, ...]


class AccountRiskEvaluator:
    """Evaluate caller-owned equity baselines and account-wide limits."""

    def __init__(self, settings: RiskConstitutionSettings) -> None:
        self._settings = settings

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        context: AccountRiskContext,
        evaluated_at: datetime,
    ) -> AccountRiskAssessment:
        """Return risk state, metrics, and every deterministic account rejection."""
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)
        reasons: list[RiskReason] = []
        expected_ref = account_fingerprint(snapshot.account.account_id, snapshot.account.server)

        if context.cycle_id != snapshot.cycle_id or context.snapshot_id != snapshot.snapshot_id:
            reasons.append(
                risk_reason(
                    RiskReasonCode.TRACEABILITY_MISMATCH,
                    "account context does not belong to the snapshot trace",
                )
            )
        if context.account_ref != expected_ref:
            reasons.append(
                risk_reason(
                    RiskReasonCode.ACCOUNT_CONTEXT_MISMATCH,
                    "account context does not match the snapshot account",
                )
            )
        if context.context_as_of > evaluated_at:
            reasons.append(
                risk_reason(
                    RiskReasonCode.ACCOUNT_CONTEXT_FUTURE_DATED,
                    "account context is later than the evaluation timestamp",
                )
            )
        if context.context_as_of < snapshot.snapshot_completed_at:
            reasons.append(
                risk_reason(
                    RiskReasonCode.ACCOUNT_CONTEXT_PREDATES_SNAPSHOT,
                    "account context predates snapshot completion",
                )
            )
        if context.trading_day_started_at > context.context_as_of:
            reasons.append(
                risk_reason(
                    RiskReasonCode.TRADING_DAY_CONTEXT_INVALID,
                    "trading-day start is later than account context",
                )
            )
        if context.account_open_position_count < len(snapshot.open_positions):
            reasons.append(
                risk_reason(
                    RiskReasonCode.ACCOUNT_POSITION_COUNT_INCONSISTENT,
                    "account-wide position count is below the snapshot symbol count",
                )
            )
        if context.account_open_position_count >= self._settings.maximum_open_positions:
            reasons.append(
                risk_reason(
                    RiskReasonCode.MAXIMUM_POSITIONS_REACHED,
                    "maximum concurrent position count has been reached",
                )
            )

        equity = snapshot.account.equity
        effective_peak = max(context.cash_flow_adjusted_peak_equity, equity)
        drawdown_amount = max(Decimal("0"), effective_peak - equity)
        drawdown_percent = drawdown_amount / effective_peak * _ONE_HUNDRED
        daily_loss_amount = max(Decimal("0"), context.adjusted_day_start_equity - equity)
        daily_loss_percent = (
            daily_loss_amount / context.adjusted_day_start_equity * _ONE_HUNDRED
        )

        state = self._drawdown_state(drawdown_percent)
        if equity <= 0:
            reasons.append(
                risk_reason(
                    RiskReasonCode.NON_POSITIVE_EQUITY,
                    "account equity must be positive",
                )
            )
            state = RiskState.HALTED
        if daily_loss_percent >= self._settings.maximum_daily_loss_percent:
            reasons.append(
                risk_reason(
                    RiskReasonCode.DAILY_LOSS_LIMIT_REACHED,
                    "daily loss limit has been reached",
                )
            )
            state = RiskState.HALTED
        if drawdown_percent >= self._settings.drawdown_stop_percent:
            reasons.append(
                risk_reason(
                    RiskReasonCode.MAXIMUM_DRAWDOWN_REACHED,
                    "maximum cash-flow-adjusted drawdown has been reached",
                )
            )
            state = RiskState.HALTED

        permitted_risk_percent = (
            Decimal("0")
            if state is RiskState.HALTED
            else self._settings.normal_risk_percent
            if state is RiskState.NORMAL
            else self._settings.minimum_risk_percent
        )
        metrics = AccountRiskMetrics(
            account_ref=context.account_ref,
            current_equity=equity,
            effective_peak_equity=effective_peak,
            drawdown_amount=drawdown_amount,
            drawdown_percent=drawdown_percent,
            daily_loss_amount=daily_loss_amount,
            daily_loss_percent=daily_loss_percent,
            account_open_position_count=context.account_open_position_count,
            permitted_risk_percent=permitted_risk_percent,
        )
        return AccountRiskAssessment(state=state, metrics=metrics, reasons=tuple(reasons))

    def _drawdown_state(self, drawdown_percent: Decimal) -> RiskState:
        if drawdown_percent >= self._settings.drawdown_stop_percent:
            return RiskState.HALTED
        if drawdown_percent >= self._settings.drawdown_safe_mode_percent:
            return RiskState.SAFE_MODE
        if drawdown_percent >= self._settings.drawdown_warning_percent:
            return RiskState.CAUTION
        return RiskState.NORMAL
