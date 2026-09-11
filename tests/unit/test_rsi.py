from decimal import Decimal

from ai_trading_team.features.indicators import rsi_series


def test_rsi14_known_monotonic_gain_vector_is_100() -> None:
    closes = tuple(Decimal(index) for index in range(15))

    assert rsi_series(closes, 14)[-1] == Decimal("100")


def test_rsi_uses_wilder_smoothing_for_subsequent_values() -> None:
    closes = tuple(Decimal(value) for value in (1, 2, 3, 2, 4))
    result = rsi_series(closes, 3)

    assert result[3] is not None and result[3].quantize(Decimal("0.00000001")) == Decimal(
        "66.66666667"
    )
    assert result[4] is not None and result[4].quantize(Decimal("0.00000001")) == Decimal(
        "83.33333333"
    )


def test_flat_rsi_vector_has_neutral_defined_value() -> None:
    assert rsi_series((Decimal("7"),) * 15, 14)[-1] == Decimal("50")
