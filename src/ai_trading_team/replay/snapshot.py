"""Historical construction of the existing strict M2 MarketSnapshot boundary."""

from datetime import datetime, timedelta

from pydantic import ValidationError

from ai_trading_team.config.settings import MarketDataSettings
from ai_trading_team.market.freshness import assess_freshness
from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.replay.protocols import DecisionDataView
from ai_trading_team.schemas.enums import FreshnessState, ReplayErrorCategory, Timeframe
from ai_trading_team.schemas.historical import HistoricalCandle
from ai_trading_team.schemas.market import (
    MarketSnapshot,
    SnapshotCandles,
    SnapshotConsistencyMetadata,
    SnapshotFreshness,
    SnapshotSourceTimestamps,
)
from ai_trading_team.schemas.mt5 import MT5Candle


class HistoricalSnapshotBuilder:
    """Maps a capped historical view into the unchanged accepted M2 contract."""

    def __init__(self, settings: MarketDataSettings) -> None:
        self._settings = settings

    def build(
        self,
        view: DecisionDataView,
        *,
        cycle_id: str,
        snapshot_id: str,
        symbol: str,
        primary_timeframe: Timeframe,
    ) -> MarketSnapshot:
        cutoff = view.decision_cutoff
        try:
            historical = {
                Timeframe.M15: view.completed_candles(
                    symbol, Timeframe.M15, self._settings.m15_candle_count
                ),
                Timeframe.H1: view.completed_candles(
                    symbol, Timeframe.H1, self._settings.h1_candle_count
                ),
                Timeframe.H4: view.completed_candles(
                    symbol, Timeframe.H4, self._settings.h4_candle_count
                ),
            }
            if any(not candles for candles in historical.values()):
                raise ReplayError(
                    ReplayErrorCategory.SNAPSHOT_REPRODUCTION_FAILURE,
                    "all M15, H1, and H4 completed histories are required",
                )
            candles = {
                timeframe: tuple(self._to_snapshot_candle(item, cutoff) for item in items)
                for timeframe, items in historical.items()
            }
            observation = view.snapshot_observations(symbol)
            symbol_info = observation.symbol_info.model_copy(update={"retrieved_at": cutoff})
            tick = observation.tick.model_copy(update={"retrieved_at": cutoff})
            account = observation.account.model_copy(update={"retrieved_at": cutoff})
            positions = tuple(
                position.model_copy(update={"retrieved_at": cutoff})
                for position in observation.open_positions
                if position.symbol == symbol
            )
            source_times = SnapshotSourceTimestamps(
                symbol_info=cutoff,
                account=cutoff,
                m15_candles=cutoff,
                h1_candles=cutoff,
                h4_candles=cutoff,
                positions=cutoff,
                tick=cutoff,
            )
            tick_freshness = assess_freshness(
                    tick.source_time,
                    cutoff,
                    timedelta(seconds=self._settings.max_tick_age_seconds),
                )
            account_freshness = assess_freshness(
                    cutoff,
                    cutoff,
                    timedelta(seconds=self._settings.max_account_age_seconds),
                )
            m15_freshness = assess_freshness(
                    candles[Timeframe.M15][-1].open_time + timedelta(minutes=15),
                    cutoff,
                    timedelta(seconds=self._settings.max_m15_candle_age_seconds),
                )
            h1_freshness = assess_freshness(
                    candles[Timeframe.H1][-1].open_time + timedelta(hours=1),
                    cutoff,
                    timedelta(seconds=self._settings.max_h1_candle_age_seconds),
                )
            h4_freshness = assess_freshness(
                    candles[Timeframe.H4][-1].open_time + timedelta(hours=4),
                    cutoff,
                    timedelta(seconds=self._settings.max_h4_candle_age_seconds),
                )
            observations = (
                tick_freshness,
                account_freshness,
                m15_freshness,
                h1_freshness,
                h4_freshness,
            )
            freshness = SnapshotFreshness(
                tick=tick_freshness,
                account=account_freshness,
                m15_candles=m15_freshness,
                h1_candles=h1_freshness,
                h4_candles=h4_freshness,
                overall=(
                    FreshnessState.STALE
                    if any(item.state is FreshnessState.STALE for item in observations)
                    else FreshnessState.FRESH
                ),
            )
            return MarketSnapshot(
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                symbol=symbol,
                primary_timeframe=primary_timeframe,
                snapshot_started_at=cutoff,
                snapshot_completed_at=cutoff,
                symbol_info=symbol_info,
                tick=tick,
                spread=tick.spread,
                candles=SnapshotCandles(
                    m15=candles[Timeframe.M15],
                    h1=candles[Timeframe.H1],
                    h4=candles[Timeframe.H4],
                ),
                account=account,
                open_positions=positions,
                consistency=SnapshotConsistencyMetadata(
                    source_timestamps=source_times,
                    snapshot_duration=timedelta(0),
                    freshness=freshness,
                ),
            )
        except ReplayError:
            raise
        except (ValidationError, ValueError, KeyError) as exc:
            raise ReplayError(
                ReplayErrorCategory.SNAPSHOT_REPRODUCTION_FAILURE,
                "historical observations cannot reproduce a valid MarketSnapshot",
            ) from exc

    @staticmethod
    def _to_snapshot_candle(
        item: HistoricalCandle, cutoff: datetime
    ) -> MT5Candle:
        if (
            item.tick_volume is None
            or item.broker_spread_points is None
            or item.real_volume is None
        ):
            raise ReplayError(
                ReplayErrorCategory.MISSING_AS_OF_OBSERVATION,
                "snapshot reproduction requires accepted candle volume/spread metadata",
            )
        return MT5Candle(
            retrieved_at=cutoff,
            symbol=item.symbol,
            timeframe=item.timeframe,
            open_time=item.open_time,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            tick_volume=item.tick_volume,
            broker_spread_points=item.broker_spread_points,
            real_volume=item.real_volume,
        )
