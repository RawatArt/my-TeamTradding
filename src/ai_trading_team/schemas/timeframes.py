"""Canonical deterministic semantics for supported market-data timeframes."""

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType
from typing import Final

from ai_trading_team.schemas.enums import Timeframe

TIMEFRAME_DURATIONS: Final[Mapping[Timeframe, timedelta]] = MappingProxyType(
    {
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
    }
)


def timeframe_duration(timeframe: Timeframe) -> timedelta:
    """Return the single canonical duration for an M2-supported timeframe."""
    return TIMEFRAME_DURATIONS[timeframe]
