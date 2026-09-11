from decimal import Decimal

from tests.fakes.features import indicator_candles

from ai_trading_team.features.geometry import candle_geometry


def test_latest_candle_geometry_uses_exact_decimal_arithmetic() -> None:
    candle = indicator_candles((Decimal("10"),))[0].model_copy(
        update={
            "open": Decimal("10"),
            "high": Decimal("15"),
            "low": Decimal("8"),
            "close": Decimal("12"),
        }
    )

    result = candle_geometry(candle)

    assert result.candle_range == Decimal("7")
    assert result.real_body == Decimal("2")
    assert result.upper_wick == Decimal("3")
    assert result.lower_wick == Decimal("2")
    assert result.body_range_ratio is not None
    assert result.body_range_ratio.quantize(Decimal("0.00000001")) == Decimal("0.28571429")


def test_zero_range_candle_has_no_fabricated_ratio() -> None:
    candle = indicator_candles((Decimal("10"),), half_range=Decimal("0"))[0]

    result = candle_geometry(candle)

    assert result.candle_range == 0
    assert result.body_range_ratio is None
