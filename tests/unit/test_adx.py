from decimal import Decimal

from tests.fakes.features import indicator_candles

from ai_trading_team.features.indicators import adx_series


def test_adx14_known_unidirectional_vector_is_100() -> None:
    candles = indicator_candles(tuple(Decimal(index) for index in range(28)))

    assert adx_series(candles, 14)[-1] == Decimal("100")


def test_adx14_requires_28_candles() -> None:
    candles = indicator_candles(tuple(Decimal(index) for index in range(27)))

    assert adx_series(candles, 14) == (None,) * 27


def test_flat_adx_vector_has_defined_zero_strength() -> None:
    candles = indicator_candles((Decimal("10"),) * 28)

    assert adx_series(candles, 14)[-1] == Decimal("0")
