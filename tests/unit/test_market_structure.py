from decimal import Decimal

from tests.fakes.features import indicator_candles

from ai_trading_team.features.structure import (
    latest_confirmed_swing_high,
    latest_confirmed_swing_low,
    recent_range,
)
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.mt5 import MT5Candle
from ai_trading_team.schemas.timeframes import timeframe_duration


def structured_candles() -> tuple[MT5Candle, ...]:
    candles = indicator_candles((Decimal("0"),) * 7)
    highs = (1, 2, 5, 2, 1, 4, 1)
    lows = (-1, -2, -5, -2, -1, -4, -1)
    return tuple(
        candle.model_copy(update={"high": Decimal(highs[index]), "low": Decimal(lows[index])})
        for index, candle in enumerate(candles)
    )


def test_swings_require_strict_left_and_right_confirmation() -> None:
    candles = structured_candles()

    high = latest_confirmed_swing_high(candles, Timeframe.M15, 2, 2)
    low = latest_confirmed_swing_low(candles, Timeframe.M15, 2, 2)

    assert high is not None and high.price == Decimal("5")
    assert low is not None and low.price == Decimal("-5")
    assert high.confirmed_at == candles[4].open_time + timeframe_duration(Timeframe.M15)


def test_unconfirmed_recent_candidate_is_not_exposed() -> None:
    candles = structured_candles()

    high = latest_confirmed_swing_high(candles, Timeframe.M15, 2, 2)

    assert high is not None
    assert high.candle_open_at == candles[2].open_time
    assert high.price != candles[5].high


def test_tied_extreme_is_not_a_strict_swing() -> None:
    candles = tuple(
        item.model_copy(update={"high": Decimal("2"), "low": Decimal("-2")})
        for item in indicator_candles((Decimal("0"),) * 5)
    )

    assert latest_confirmed_swing_high(candles, Timeframe.M15, 2, 2) is None
    assert latest_confirmed_swing_low(candles, Timeframe.M15, 2, 2) is None


def test_recent_range_uses_only_latest_fixed_window() -> None:
    candles = structured_candles()

    assert recent_range(candles, 3) == (Decimal("4"), Decimal("-4"))
    assert recent_range(candles, 8) is None
