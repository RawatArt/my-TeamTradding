from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.market import symbol_info

from ai_trading_team.risk import PositionSizer
from ai_trading_team.schemas.enums import PositionSizingStatus, RiskReasonCode
from ai_trading_team.schemas.mt5 import MT5SymbolInfo
from ai_trading_team.schemas.risk import PositionSizingResult


def changed_symbol_info(**changes: object) -> MT5SymbolInfo:
    payload = symbol_info().model_dump(mode="python")
    payload.update(changes)
    return MT5SymbolInfo.model_validate(payload)


def test_position_size_rounds_down_on_grid_anchored_at_minimum() -> None:
    outcome = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00123"),
        symbol_info=symbol_info(),
    )

    assert not outcome.reasons
    assert outcome.result is not None
    assert outcome.result.status is PositionSizingStatus.APPROVED
    assert outcome.result.allowed_risk_amount == Decimal("50.00")
    assert outcome.result.raw_volume == Decimal("50.00") / Decimal("123")
    assert outcome.result.selected_volume == Decimal("0.40")
    assert outcome.result.estimated_risk_amount == Decimal("49.20")


def test_volume_grid_can_be_anchored_at_nonzero_nonstep_minimum() -> None:
    metadata = changed_symbol_info(
        volume_min=Decimal("0.03"), volume_step=Decimal("0.02")
    )
    outcome = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00123"),
        symbol_info=metadata,
    )

    assert outcome.result is not None
    assert outcome.result.selected_volume == Decimal("0.39")
    assert (outcome.result.selected_volume - Decimal("0.03")) % Decimal("0.02") == 0


def test_minimum_volume_is_rejected_when_it_exceeds_allowed_risk() -> None:
    outcome = PositionSizer().calculate(
        equity=Decimal("50"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00100"),
        symbol_info=symbol_info(),
    )

    assert outcome.result is not None
    assert outcome.result.status is PositionSizingStatus.REJECTED
    assert outcome.result.selected_volume is None
    assert outcome.reasons[0].code is RiskReasonCode.MINIMUM_VOLUME_EXCEEDS_RISK


def test_tick_value_is_used_once_and_contract_size_is_not_double_counted() -> None:
    first = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00100"),
        symbol_info=changed_symbol_info(trade_contract_size=Decimal("1")),
    )
    second = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00100"),
        symbol_info=changed_symbol_info(trade_contract_size=Decimal("100000")),
    )

    assert first.result is not None and second.result is not None
    assert first.result.selected_volume == second.result.selected_volume
    assert first.result.estimated_risk_amount == second.result.estimated_risk_amount


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trade_tick_size", Decimal("0")),
        ("trade_tick_value", Decimal("0")),
        ("trade_contract_size", Decimal("0")),
        ("volume_min", Decimal("0")),
        ("volume_step", Decimal("0")),
    ],
)
def test_invalid_broker_sizing_metadata_is_rejected(field: str, value: Decimal) -> None:
    outcome = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00100"),
        symbol_info=changed_symbol_info(**{field: value}),
    )

    assert outcome.result is None
    assert outcome.reasons[0].code is RiskReasonCode.INVALID_BROKER_RISK_METADATA


def test_approved_sizing_schema_rejects_broken_final_invariants() -> None:
    outcome = PositionSizer().calculate(
        equity=Decimal("10000"),
        risk_percent=Decimal("0.50"),
        stop_distance=Decimal("0.00123"),
        symbol_info=symbol_info(),
    )
    assert outcome.result is not None
    payload = outcome.result.model_dump(mode="python")
    payload["selected_volume"] = Decimal("0.405")
    payload["estimated_risk_amount"] = Decimal("49.815")

    with pytest.raises(ValidationError, match="align"):
        PositionSizingResult.model_validate(payload)
