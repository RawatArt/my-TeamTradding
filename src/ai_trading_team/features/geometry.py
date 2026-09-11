"""Deterministic geometry of the latest completed candle."""

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from ai_trading_team.features.definitions import DECIMAL_PRECISION, DECIMAL_ROUNDING
from ai_trading_team.schemas.mt5 import MT5Candle


@dataclass(frozen=True, slots=True)
class CandleGeometry:
    candle_range: Decimal
    real_body: Decimal
    upper_wick: Decimal
    lower_wick: Decimal
    body_range_ratio: Decimal | None


def candle_geometry(candle: MT5Candle) -> CandleGeometry:
    """Calculate factual OHLC geometry with no directional interpretation."""
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
        candle_range = candle.high - candle.low
        real_body = abs(candle.close - candle.open)
        upper_wick = candle.high - max(candle.open, candle.close)
        lower_wick = min(candle.open, candle.close) - candle.low
        ratio = None if candle_range == 0 else real_body / candle_range
    return CandleGeometry(
        candle_range=candle_range,
        real_body=real_body,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        body_range_ratio=ratio,
    )
