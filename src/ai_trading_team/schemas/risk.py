"""Immutable M3 account-risk, sizing, and final-decision contracts."""

from datetime import UTC, datetime
from typing import Self

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    AccountReference,
    CoreModel,
    CycleId,
    FiniteDecimal,
    Identifier,
    NonNegativeDecimal,
    PerTradeRiskPercentage,
    PositiveDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
    TraceableRecord,
)
from ai_trading_team.schemas.enums import (
    PositionSizingStatus,
    RiskDecisionStatus,
    RiskReasonCode,
    RiskState,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class RiskReason(CoreModel):
    """One stable reason contributing to a rejection or halt."""

    code: RiskReasonCode
    message: str = Field(min_length=1, max_length=512)


class AccountRiskContext(CoreModel):
    """Caller-owned stateless baselines for one account and snapshot."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    account_ref: AccountReference
    context_as_of: datetime
    trading_day_started_at: datetime
    cash_flow_adjusted_peak_equity: PositiveDecimal
    adjusted_day_start_equity: PositiveDecimal
    account_open_position_count: NonNegativeInt

    _normalize_utc = field_validator("context_as_of", "trading_day_started_at")(_utc)

    @model_validator(mode="after")
    def validate_trading_day_window(self) -> Self:
        if self.trading_day_started_at > self.context_as_of:
            raise ValueError("trading_day_started_at must not be after context_as_of")
        return self


class AccountRiskMetrics(CoreModel):
    """Deterministic account calculations retained with every decision."""

    account_ref: AccountReference
    current_equity: FiniteDecimal
    effective_peak_equity: PositiveDecimal
    drawdown_amount: NonNegativeDecimal
    drawdown_percent: NonNegativeDecimal
    daily_loss_amount: NonNegativeDecimal
    daily_loss_percent: NonNegativeDecimal
    account_open_position_count: NonNegativeInt
    permitted_risk_percent: PerTradeRiskPercentage


class PositionSizingResult(CoreModel):
    """Auditable stop-risk sizing result with final broker-grid invariants."""

    status: PositionSizingStatus
    risk_percent: PerTradeRiskPercentage
    allowed_risk_amount: PositiveDecimal
    stop_distance: PositiveDecimal
    tick_size: PositiveDecimal
    tick_value: PositiveDecimal
    trade_contract_size: PositiveDecimal
    ticks_to_stop: PositiveDecimal
    monetary_loss_per_lot: PositiveDecimal
    raw_volume: PositiveDecimal
    volume_min: PositiveDecimal
    volume_max: PositiveDecimal
    volume_step: PositiveDecimal
    minimum_volume_risk_amount: PositiveDecimal
    selected_volume: PositiveDecimal | None = None
    estimated_risk_amount: PositiveDecimal | None = None

    @model_validator(mode="after")
    def validate_calculation_and_final_volume(self) -> Self:
        if self.volume_max < self.volume_min:
            raise ValueError("volume_max must be greater than or equal to volume_min")
        if self.ticks_to_stop != self.stop_distance / self.tick_size:
            raise ValueError("ticks_to_stop must match stop distance and tick size")
        if self.monetary_loss_per_lot != self.ticks_to_stop * self.tick_value:
            raise ValueError("monetary_loss_per_lot must match tick loss")
        if self.raw_volume != self.allowed_risk_amount / self.monetary_loss_per_lot:
            raise ValueError("raw_volume must match allowed risk and loss per lot")
        if self.minimum_volume_risk_amount != self.monetary_loss_per_lot * self.volume_min:
            raise ValueError("minimum_volume_risk_amount must match minimum volume")

        if self.status is PositionSizingStatus.REJECTED:
            if self.selected_volume is not None or self.estimated_risk_amount is not None:
                raise ValueError("rejected sizing must not select a volume")
            return self

        if self.selected_volume is None or self.estimated_risk_amount is None:
            raise ValueError("approved sizing requires selected volume and estimated risk")
        if not self.volume_min <= self.selected_volume <= self.volume_max:
            raise ValueError("selected volume must be within broker bounds")
        if (self.selected_volume - self.volume_min) % self.volume_step != 0:
            raise ValueError("selected volume must align to the broker volume step")
        if self.estimated_risk_amount != self.monetary_loss_per_lot * self.selected_volume:
            raise ValueError("estimated risk must match selected volume")
        if self.estimated_risk_amount > self.allowed_risk_amount:
            raise ValueError("estimated risk must not exceed allowed risk")
        return self


class RiskDecision(TraceableRecord):
    """Final deterministic M3 decision; this is not an executable order."""

    snapshot_id: SnapshotId
    proposal_id: Identifier
    account_ref: AccountReference
    symbol: Symbol
    status: RiskDecisionStatus
    risk_state: RiskState
    reasons: tuple[RiskReason, ...]
    account_metrics: AccountRiskMetrics
    position_sizing: PositionSizingResult | None = None

    @model_validator(mode="after")
    def validate_decision_consistency(self) -> Self:
        if self.account_metrics.account_ref != self.account_ref:
            raise ValueError("decision account reference must match account metrics")
        if self.status is RiskDecisionStatus.APPROVED:
            if self.reasons:
                raise ValueError("approved decision must not contain rejection reasons")
            if (
                self.position_sizing is None
                or self.position_sizing.status is not PositionSizingStatus.APPROVED
            ):
                raise ValueError("approved decision requires approved position sizing")
            if self.risk_state is RiskState.HALTED:
                raise ValueError("HALTED risk state cannot approve a proposal")
            return self

        if not self.reasons:
            raise ValueError("rejected or halted decision requires at least one reason")
        if self.status is RiskDecisionStatus.HALTED and self.risk_state is not RiskState.HALTED:
            raise ValueError("HALTED decision requires HALTED risk state")
        if self.risk_state is RiskState.HALTED and self.status is not RiskDecisionStatus.HALTED:
            raise ValueError("HALTED risk state requires HALTED decision")
        if (
            self.position_sizing is not None
            and self.position_sizing.status is PositionSizingStatus.APPROVED
        ):
            raise ValueError("a non-approved decision cannot retain approved position sizing")
        return self
