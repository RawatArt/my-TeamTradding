"""Decimal-only position sizing on broker-provided volume grids."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from pydantic import ValidationError

from ai_trading_team.risk.reasons import risk_reason
from ai_trading_team.schemas.enums import PositionSizingStatus, RiskReasonCode
from ai_trading_team.schemas.mt5 import MT5SymbolInfo
from ai_trading_team.schemas.risk import PositionSizingResult, RiskReason

_ONE_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class PositionSizingOutcome:
    """Sizing result plus stable failure reasons."""

    result: PositionSizingResult | None
    reasons: tuple[RiskReason, ...]


class PositionSizer:
    """Size stop-loss exposure without pip or contract-size assumptions."""

    def calculate(
        self,
        *,
        equity: Decimal,
        risk_percent: Decimal,
        stop_distance: Decimal,
        symbol_info: MT5SymbolInfo,
    ) -> PositionSizingOutcome:
        tick_size = symbol_info.trade_tick_size
        tick_value = symbol_info.trade_tick_value
        contract_size = symbol_info.trade_contract_size
        volume_min = symbol_info.volume_min
        volume_max = symbol_info.volume_max
        volume_step = symbol_info.volume_step
        if (
            equity <= 0
            or risk_percent <= 0
            or stop_distance <= 0
            or tick_size <= 0
            or tick_value <= 0
            or contract_size <= 0
            or volume_min <= 0
            or volume_max < volume_min
            or volume_step <= 0
        ):
            return PositionSizingOutcome(
                result=None,
                reasons=(
                    risk_reason(
                        RiskReasonCode.INVALID_BROKER_RISK_METADATA,
                        "position sizing inputs and broker metadata must be positive and coherent",
                    ),
                ),
            )

        allowed_risk = equity * risk_percent / _ONE_HUNDRED
        ticks_to_stop = stop_distance / tick_size
        loss_per_lot = ticks_to_stop * tick_value
        raw_volume = allowed_risk / loss_per_lot
        minimum_volume_risk = loss_per_lot * volume_min
        base = dict(
            risk_percent=risk_percent,
            allowed_risk_amount=allowed_risk,
            stop_distance=stop_distance,
            tick_size=tick_size,
            tick_value=tick_value,
            trade_contract_size=contract_size,
            ticks_to_stop=ticks_to_stop,
            monetary_loss_per_lot=loss_per_lot,
            raw_volume=raw_volume,
            volume_min=volume_min,
            volume_max=volume_max,
            volume_step=volume_step,
            minimum_volume_risk_amount=minimum_volume_risk,
        )
        if minimum_volume_risk > allowed_risk:
            result = PositionSizingResult(status=PositionSizingStatus.REJECTED, **base)
            return PositionSizingOutcome(
                result=result,
                reasons=(
                    risk_reason(
                        RiskReasonCode.MINIMUM_VOLUME_EXCEEDS_RISK,
                        "broker minimum volume would exceed allowed monetary risk",
                    ),
                ),
            )

        capped_volume = min(raw_volume, volume_max)
        increments = ((capped_volume - volume_min) / volume_step).to_integral_value(
            rounding=ROUND_FLOOR
        )
        selected_volume = volume_min + increments * volume_step
        estimated_risk = loss_per_lot * selected_volume
        try:
            result = PositionSizingResult(
                status=PositionSizingStatus.APPROVED,
                selected_volume=selected_volume,
                estimated_risk_amount=estimated_risk,
                **base,
            )
        except ValidationError:
            rejected = PositionSizingResult(status=PositionSizingStatus.REJECTED, **base)
            return PositionSizingOutcome(
                result=rejected,
                reasons=(
                    risk_reason(
                        RiskReasonCode.POSITION_SIZE_INVARIANT_FAILED,
                        "final broker-volume invariants failed",
                    ),
                ),
            )
        return PositionSizingOutcome(result=result, reasons=())
