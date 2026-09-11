"""Defense-in-depth validation for completed M2 candle inputs."""

from pydantic import ValidationError

from ai_trading_team.features.errors import FeatureEngineError
from ai_trading_team.schemas.enums import FeatureErrorCategory, Timeframe
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5Candle
from ai_trading_team.schemas.timeframes import timeframe_duration


def revalidate_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot:
    """Re-run the complete boundary validation even for constructed model instances."""
    if not isinstance(snapshot, MarketSnapshot):
        raise FeatureEngineError(
            FeatureErrorCategory.INVALID_SNAPSHOT,
            "feature input is not a MarketSnapshot",
        )
    try:
        return MarketSnapshot.model_validate(snapshot.model_dump(mode="python"))
    except ValidationError as exc:
        raise FeatureEngineError(
            FeatureErrorCategory.INVALID_SNAPSHOT,
            "MarketSnapshot failed structural validation",
        ) from exc


def validate_candles(
    snapshot: MarketSnapshot,
    timeframe: Timeframe,
    candles: tuple[MT5Candle, ...],
) -> None:
    """Reject wrong identity, ordering, future, or incomplete source candles."""
    if not candles:
        raise FeatureEngineError(
            FeatureErrorCategory.INVALID_SNAPSHOT,
            "snapshot candle collection is empty",
        )
    previous_open = None
    for candle in candles:
        if candle.symbol != snapshot.symbol:
            raise FeatureEngineError(
                FeatureErrorCategory.SYMBOL_MISMATCH,
                "source candle symbol does not match snapshot symbol",
            )
        if candle.timeframe is not timeframe:
            raise FeatureEngineError(
                FeatureErrorCategory.TIMEFRAME_MISMATCH,
                "source candle timeframe does not match its collection",
            )
        if previous_open is not None and candle.open_time <= previous_open:
            raise FeatureEngineError(
                FeatureErrorCategory.INVALID_CANDLE_ORDER,
                "source candle times must be unique and strictly increasing",
            )
        if candle.open_time > snapshot.snapshot_completed_at:
            raise FeatureEngineError(
                FeatureErrorCategory.FUTURE_CANDLE,
                "source candle opens after snapshot completion",
            )
        if candle.open_time + timeframe_duration(timeframe) > snapshot.snapshot_completed_at:
            raise FeatureEngineError(
                FeatureErrorCategory.INCOMPLETE_CANDLE,
                "source candle was incomplete at snapshot completion",
            )
        previous_open = candle.open_time
