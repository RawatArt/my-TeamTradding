"""Confirmed market-structure facts without signal semantics."""

from collections.abc import Sequence
from decimal import Decimal

from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.features import SwingPoint
from ai_trading_team.schemas.mt5 import MT5Candle
from ai_trading_team.schemas.timeframes import timeframe_duration


def latest_confirmed_swing_high(
    candles: Sequence[MT5Candle],
    timeframe: Timeframe,
    left_bars: int,
    right_bars: int,
) -> SwingPoint | None:
    return _latest_confirmed_swing(candles, timeframe, left_bars, right_bars, high=True)


def latest_confirmed_swing_low(
    candles: Sequence[MT5Candle],
    timeframe: Timeframe,
    left_bars: int,
    right_bars: int,
) -> SwingPoint | None:
    return _latest_confirmed_swing(candles, timeframe, left_bars, right_bars, high=False)


def recent_range(
    candles: Sequence[MT5Candle], lookback: int
) -> tuple[Decimal, Decimal] | None:
    """Return high/low of the latest complete fixed-size window."""
    if lookback <= 0:
        raise ValueError("recent range lookback must be positive")
    if len(candles) < lookback:
        return None
    window = candles[-lookback:]
    return max(item.high for item in window), min(item.low for item in window)


def _latest_confirmed_swing(
    candles: Sequence[MT5Candle],
    timeframe: Timeframe,
    left_bars: int,
    right_bars: int,
    *,
    high: bool,
) -> SwingPoint | None:
    if left_bars <= 0 or right_bars <= 0:
        raise ValueError("swing confirmation windows must be positive")
    if len(candles) < left_bars + right_bars + 1:
        return None
    def level(item: MT5Candle) -> Decimal:
        return item.high if high else item.low

    for index in range(len(candles) - right_bars - 1, left_bars - 1, -1):
        candidate = level(candles[index])
        left = (level(item) for item in candles[index - left_bars : index])
        right = (level(item) for item in candles[index + 1 : index + right_bars + 1])
        comparison = all(candidate > item for item in (*left, *right)) if high else all(
            candidate < item for item in (*left, *right)
        )
        if comparison:
            confirmation_candle = candles[index + right_bars]
            return SwingPoint(
                price=candidate,
                candle_open_at=candles[index].open_time,
                confirmed_at=confirmation_candle.open_time + timeframe_duration(timeframe),
                left_bars=left_bars,
                right_bars=right_bars,
            )
    return None
