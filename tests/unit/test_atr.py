from decimal import Decimal

from tests.fakes.features import indicator_candles

from ai_trading_team.features.indicators import atr_series


def test_atr14_known_constant_true_range_vector_is_two() -> None:
    candles = indicator_candles(tuple(Decimal(index) / 2 for index in range(15)))

    assert atr_series(candles, 14)[-1] == Decimal("2")


def test_atr_requires_previous_close_without_guessing_pre_window_value() -> None:
    candles = indicator_candles((Decimal("10"),) * 14)

    assert atr_series(candles, 14) == (None,) * 14

