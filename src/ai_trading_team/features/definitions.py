"""Versioned M7 mathematical definitions and required-history rules."""

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from ai_trading_team.schemas.features import FeatureDefinitionVersions

FEATURE_ENGINE_VERSION: Final = "1.0.0"
FEATURE_SET_VERSION: Final = "1.0.0"
CANONICALIZATION_VERSION: Final = "1.0.0"
DECIMAL_PRECISION: Final = 50
DECIMAL_ROUNDING: Final = ROUND_HALF_EVEN
INDEX_QUANTUM: Final = Decimal("0.00000001")

EMA_PERIODS: Final = (20, 50, 200)
RSI_PERIOD: Final = 14
ATR_PERIOD: Final = 14
ADX_PERIOD: Final = 14

DEFINITION_VERSIONS: Final = FeatureDefinitionVersions(
    ema="1.0.0",
    rsi="1.0.0",
    atr="1.0.0",
    adx="1.0.0",
    candle_geometry="1.0.0",
    confirmed_swing="1.0.0",
    recent_range="1.0.0",
    signed_distance="1.0.0",
)


def geometry_required_candles() -> int:
    return 1


def ema_required_candles(period: int) -> int:
    return period


def rsi_required_candles(period: int = RSI_PERIOD) -> int:
    return period + 1


def atr_required_candles(period: int = ATR_PERIOD) -> int:
    return period + 1


def adx_required_candles(period: int = ADX_PERIOD) -> int:
    return period * 2


def recent_range_required_candles(lookback: int) -> int:
    return lookback


def confirmed_swing_required_candles(left_bars: int, right_bars: int) -> int:
    return left_bars + right_bars + 1

