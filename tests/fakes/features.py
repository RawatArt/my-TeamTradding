"""Deterministic completed-candle fixtures for M7 feature tests."""

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from ai_trading_team.config import MarketDataSettings
from ai_trading_team.market import MarketDataService
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5Candle
from ai_trading_team.schemas.timeframes import timeframe_duration
from tests.fakes.market import (
    SNAPSHOT_END,
    SNAPSHOT_START,
    SYMBOL,
    FakeMarketDataSource,
    SequenceClock,
)

FEATURE_CYCLE_ID = "cycle-m7-001"
FEATURE_SNAPSHOT_ID = "snapshot-m7-001"


def generated_closes(count: int) -> tuple[Decimal, ...]:
    pattern = (0, 2, 5, 2, 0, -2, -5, -2)
    return tuple(
        Decimal("1.10000")
        + Decimal(index // len(pattern)) * Decimal("0.00010")
        + Decimal(pattern[index % len(pattern)]) * Decimal("0.00010")
        for index in range(count)
    )


def feature_candles(
    timeframe: Timeframe,
    count: int = 200,
    *,
    closes: Sequence[Decimal] | None = None,
) -> tuple[MT5Candle, ...]:
    values = tuple(closes) if closes is not None else generated_closes(count)
    if len(values) != count:
        raise ValueError("close vector must match requested candle count")
    duration = timeframe_duration(timeframe)
    first_open = SNAPSHOT_START - duration * count
    result: list[MT5Candle] = []
    for index, close in enumerate(values):
        open_price = close
        result.append(
            MT5Candle(
                retrieved_at=SNAPSHOT_START + timedelta(seconds=2),
                symbol=SYMBOL,
                timeframe=timeframe,
                open_time=first_open + duration * index,
                open=open_price,
                high=max(open_price, close) + Decimal("0.00020"),
                low=min(open_price, close) - Decimal("0.00020"),
                close=close,
                tick_volume=100 + index,
                broker_spread_points=12,
                real_volume=index,
            )
        )
    return tuple(result)


def indicator_candles(
    closes: Sequence[Decimal],
    *,
    timeframe: Timeframe = Timeframe.M15,
    half_range: Decimal = Decimal("1"),
) -> tuple[MT5Candle, ...]:
    """Create simple valid bars for independently known indicator vectors."""
    duration = timeframe_duration(timeframe)
    first_open = SNAPSHOT_START - duration * len(closes)
    return tuple(
        MT5Candle(
            retrieved_at=SNAPSHOT_START,
            symbol=SYMBOL,
            timeframe=timeframe,
            open_time=first_open + duration * index,
            open=close,
            high=close + half_range,
            low=close - half_range,
            close=close,
            tick_volume=1,
            broker_spread_points=0,
            real_volume=0,
        )
        for index, close in enumerate(closes)
    )


def feature_snapshot(
    count: int = 200,
    *,
    collections: dict[Timeframe, tuple[MT5Candle, ...]] | None = None,
) -> MarketSnapshot:
    source = FakeMarketDataSource()
    selected = collections or {
        timeframe: feature_candles(timeframe, count)
        for timeframe in (Timeframe.M15, Timeframe.H1, Timeframe.H4)
    }
    source.candle_results = selected
    settings = MarketDataSettings(
        m15_candle_count=len(selected[Timeframe.M15]),
        h1_candle_count=len(selected[Timeframe.H1]),
        h4_candle_count=len(selected[Timeframe.H4]),
    )
    return MarketDataService(
        source,
        settings,
        SYMBOL,
        clock=SequenceClock(
            SNAPSHOT_START,
            SNAPSHOT_START + timedelta(seconds=3),
            SNAPSHOT_END,
        ),
    ).build_snapshot(FEATURE_CYCLE_ID, FEATURE_SNAPSHOT_ID, Timeframe.M15)
