from datetime import timedelta

from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.timeframes import TIMEFRAME_DURATIONS, timeframe_duration


def test_canonical_timeframe_durations_cover_only_m2_timeframes() -> None:
    assert dict(TIMEFRAME_DURATIONS) == {
        Timeframe.M15: timedelta(minutes=15),
        Timeframe.H1: timedelta(hours=1),
        Timeframe.H4: timedelta(hours=4),
    }
    assert timeframe_duration(Timeframe.M15) == timedelta(minutes=15)
