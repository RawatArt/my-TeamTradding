"""Sanitized errors for M2 snapshot composition."""

from enum import StrEnum

from ai_trading_team.schemas.enums import Timeframe


class MarketDataErrorCategory(StrEnum):
    """Stable failure categories exposed by the M2 composition layer."""

    MISSING_SYMBOL = "MISSING_SYMBOL"
    STALE_TICK = "STALE_TICK"
    INSUFFICIENT_CANDLE_HISTORY = "INSUFFICIENT_CANDLE_HISTORY"
    INCONSISTENT_TIMESTAMPS = "INCONSISTENT_TIMESTAMPS"
    INVALID_TIMEFRAME_DATA = "INVALID_TIMEFRAME_DATA"
    SNAPSHOT_COMPOSITION_FAILURE = "SNAPSHOT_COMPOSITION_FAILURE"


class MarketDataError(RuntimeError):
    """Typed exception containing no raw terminal data or sensitive metadata."""

    def __init__(
        self,
        category: MarketDataErrorCategory,
        operation: str,
        message: str,
        *,
        cycle_id: str | None = None,
        snapshot_id: str | None = None,
        timeframe: Timeframe | None = None,
        cause_category: str | None = None,
    ) -> None:
        self.category = category
        self.operation = operation
        self.safe_message = message
        self.cycle_id = cycle_id
        self.snapshot_id = snapshot_id
        self.timeframe = timeframe
        self.cause_category = cause_category
        super().__init__(f"{category.value}: {message}; operation={operation}")
