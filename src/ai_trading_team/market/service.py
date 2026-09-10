"""M2 composition of typed read-only observations into one market snapshot."""

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from pydantic import TypeAdapter, ValidationError

from ai_trading_team.config.settings import MarketDataSettings
from ai_trading_team.market.errors import MarketDataError, MarketDataErrorCategory
from ai_trading_team.market.freshness import assess_freshness
from ai_trading_team.market.protocols import MarketDataSource
from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.schemas.common import CycleId, SnapshotId, Symbol
from ai_trading_team.schemas.enums import (
    DataValidityState,
    FreshnessState,
    SnapshotWarningCode,
    Timeframe,
)
from ai_trading_team.schemas.market import (
    MarketSnapshot,
    ObservationFreshness,
    SnapshotCandles,
    SnapshotConsistencyMetadata,
    SnapshotFreshness,
    SnapshotSourceTimestamps,
    SnapshotValidationWarning,
)
from ai_trading_team.schemas.mt5 import MT5Candle, MT5OpenPosition
from ai_trading_team.schemas.timeframes import timeframe_duration
from ai_trading_team.utils.logging import get_logger
from ai_trading_team.utils.time import normalize_utc, utc_now

_CYCLE_ID = TypeAdapter(CycleId)
_SNAPSHOT_ID = TypeAdapter(SnapshotId)


class MarketDataService:
    """Build immutable snapshots without evaluating whether they are tradeable."""

    def __init__(
        self,
        source: MarketDataSource,
        settings: MarketDataSettings,
        symbol: Symbol | None,
        *,
        clock: Callable[[], datetime] = utc_now,
        logger: logging.Logger | None = None,
    ) -> None:
        self._source = source
        self._settings = settings
        self._symbol = symbol
        self._clock = clock
        self._logger = logger or get_logger(__name__)

    def build_snapshot(
        self,
        cycle_id: CycleId,
        snapshot_id: SnapshotId,
        primary_timeframe: Timeframe,
    ) -> MarketSnapshot:
        """Read and validate exactly one cycle-owned snapshot."""
        try:
            cycle = _CYCLE_ID.validate_python(cycle_id)
            snapshot = _SNAPSHOT_ID.validate_python(snapshot_id)
        except ValidationError as exc:
            raise self._error(
                MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE,
                "validate_request",
                "cycle_id or snapshot_id is invalid",
                "[INVALID]",
                "[INVALID]",
            ) from exc

        symbol = self._symbol
        if symbol is None or not symbol.strip():
            raise self._error(
                MarketDataErrorCategory.MISSING_SYMBOL,
                "validate_request",
                "a configured broker symbol is required",
                cycle,
                snapshot,
            )

        try:
            started_at = self._read_clock(cycle, snapshot)
            symbol_info = self._source.get_symbol_info(symbol)
            account = self._source.get_account_info()
            m15 = self._read_candles(
                symbol, Timeframe.M15, self._settings.m15_candle_count, cycle, snapshot
            )
            h1 = self._read_candles(
                symbol, Timeframe.H1, self._settings.h1_candle_count, cycle, snapshot
            )
            h4 = self._read_candles(
                symbol, Timeframe.H4, self._settings.h4_candle_count, cycle, snapshot
            )
            returned_positions = self._source.get_positions(symbol)
            positions_retrieved_at = self._read_clock(cycle, snapshot)
            positions = tuple(item for item in returned_positions if item.symbol == symbol)
            omitted_positions = len(returned_positions) - len(positions)
            tick = self._source.get_tick(symbol)
            completed_at = self._read_clock(cycle, snapshot)

            self._validate_symbol_observations(
                symbol,
                symbol_info.symbol,
                tick.symbol,
                cycle,
                snapshot,
            )
            self._validate_observation_times(
                started_at,
                completed_at,
                symbol_info.retrieved_at,
                account.retrieved_at,
                tick.retrieved_at,
                cycle_id=cycle,
                snapshot_id=snapshot,
            )
            self._validate_tick_time(
                tick.source_time,
                tick.retrieved_at,
                completed_at,
                cycle,
                snapshot,
            )
            self._validate_candles(
                symbol, Timeframe.M15, m15, started_at, completed_at, cycle, snapshot
            )
            self._validate_candles(
                symbol, Timeframe.H1, h1, started_at, completed_at, cycle, snapshot
            )
            self._validate_candles(
                symbol, Timeframe.H4, h4, started_at, completed_at, cycle, snapshot
            )
            self._validate_positions(positions, started_at, completed_at, cycle, snapshot)

            freshness = self._freshness(
                account.retrieved_at,
                tick.source_time,
                m15,
                h1,
                h4,
                completed_at,
            )
            warnings = self._warnings(
                freshness,
                completed_at - started_at,
                omitted_positions,
            )
            source_timestamps = SnapshotSourceTimestamps(
                symbol_info=symbol_info.retrieved_at,
                account=account.retrieved_at,
                m15_candles=self._collection_retrieved_at(m15, cycle, snapshot),
                h1_candles=self._collection_retrieved_at(h1, cycle, snapshot),
                h4_candles=self._collection_retrieved_at(h4, cycle, snapshot),
                positions=positions_retrieved_at,
                tick=tick.retrieved_at,
            )
            self._validate_observation_times(
                started_at,
                completed_at,
                *source_timestamps.model_dump(mode="python").values(),
                cycle_id=cycle,
                snapshot_id=snapshot,
            )
            result = MarketSnapshot(
                cycle_id=cycle,
                snapshot_id=snapshot,
                symbol=symbol,
                primary_timeframe=primary_timeframe,
                snapshot_started_at=started_at,
                snapshot_completed_at=completed_at,
                symbol_info=symbol_info,
                tick=tick,
                spread=tick.spread,
                candles=SnapshotCandles(m15=m15, h1=h1, h4=h4),
                account=account,
                open_positions=positions,
                consistency=SnapshotConsistencyMetadata(
                    validity=DataValidityState.VALID,
                    source_timestamps=source_timestamps,
                    snapshot_duration=completed_at - started_at,
                    freshness=freshness,
                    validation_warnings=warnings,
                ),
            )
        except MarketDataError:
            raise
        except MT5ClientError as exc:
            category = (
                MarketDataErrorCategory.MISSING_SYMBOL
                if exc.category
                in {
                    MT5ErrorCategory.SYMBOL_UNAVAILABLE,
                    MT5ErrorCategory.SYMBOL_NOT_SELECTED,
                    MT5ErrorCategory.SYMBOL_INFO_ERROR,
                }
                else MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE
            )
            raise self._error(
                category,
                "build_snapshot",
                "read-only market source could not provide the snapshot",
                cycle,
                snapshot,
                cause_category=exc.category.value,
            ) from exc
        except (TypeError, ValueError) as exc:
            raise self._error(
                MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE,
                "build_snapshot",
                "snapshot failed boundary validation",
                cycle,
                snapshot,
            ) from exc
        except Exception as exc:
            raise self._error(
                MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE,
                "build_snapshot",
                "snapshot composition failed unexpectedly",
                cycle,
                snapshot,
            ) from exc

        self._logger.info(
            "market_snapshot_built",
            extra={
                "cycle_id": cycle,
                "snapshot_id": snapshot,
                "symbol": symbol,
                "freshness": result.consistency.freshness.overall.value,
            },
        )
        return result

    def _read_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int,
        cycle_id: str,
        snapshot_id: str,
    ) -> tuple[MT5Candle, ...]:
        candles = self._source.get_candles(
            symbol,
            timeframe,
            count,
            include_incomplete=False,
        )
        if len(candles) < count:
            raise self._error(
                MarketDataErrorCategory.INSUFFICIENT_CANDLE_HISTORY,
                "get_candles",
                f"{timeframe.value} returned fewer completed candles than requested",
                cycle_id,
                snapshot_id,
                timeframe=timeframe,
            )
        if len(candles) > count:
            raise self._error(
                MarketDataErrorCategory.INVALID_TIMEFRAME_DATA,
                "get_candles",
                f"{timeframe.value} returned more candles than requested",
                cycle_id,
                snapshot_id,
                timeframe=timeframe,
            )
        return candles

    def _freshness(
        self,
        account_time: datetime,
        tick_time: datetime,
        m15: tuple[MT5Candle, ...],
        h1: tuple[MT5Candle, ...],
        h4: tuple[MT5Candle, ...],
        completed_at: datetime,
    ) -> SnapshotFreshness:
        tick = assess_freshness(
            tick_time,
            completed_at,
            timedelta(seconds=self._settings.max_tick_age_seconds),
        )
        account = assess_freshness(
            account_time,
            completed_at,
            timedelta(seconds=self._settings.max_account_age_seconds),
        )
        m15_state = self._candle_freshness(
            m15, Timeframe.M15, self._settings.max_m15_candle_age_seconds, completed_at
        )
        h1_state = self._candle_freshness(
            h1, Timeframe.H1, self._settings.max_h1_candle_age_seconds, completed_at
        )
        h4_state = self._candle_freshness(
            h4, Timeframe.H4, self._settings.max_h4_candle_age_seconds, completed_at
        )
        observations = (tick, account, m15_state, h1_state, h4_state)
        overall = (
            FreshnessState.STALE
            if any(item.state is FreshnessState.STALE for item in observations)
            else FreshnessState.FRESH
        )
        return SnapshotFreshness(
            tick=tick,
            account=account,
            m15_candles=m15_state,
            h1_candles=h1_state,
            h4_candles=h4_state,
            overall=overall,
        )

    @staticmethod
    def _candle_freshness(
        candles: tuple[MT5Candle, ...],
        timeframe: Timeframe,
        maximum_age_seconds: int,
        completed_at: datetime,
    ) -> ObservationFreshness:
        latest_close = candles[-1].open_time + timeframe_duration(timeframe)
        return assess_freshness(
            latest_close,
            completed_at,
            timedelta(seconds=maximum_age_seconds),
        )

    def _warnings(
        self,
        freshness: SnapshotFreshness,
        duration: timedelta,
        omitted_positions: int,
    ) -> tuple[SnapshotValidationWarning, ...]:
        warnings: list[SnapshotValidationWarning] = []
        if freshness.tick.state is FreshnessState.STALE:
            warnings.append(
                SnapshotValidationWarning(
                    code=SnapshotWarningCode.STALE_TICK,
                    message="tick is valid but older than the configured freshness threshold",
                )
            )
        if freshness.account.state is FreshnessState.STALE:
            warnings.append(
                SnapshotValidationWarning(
                    code=SnapshotWarningCode.STALE_ACCOUNT,
                    message="account observation is valid but stale",
                )
            )
        for timeframe, observation in (
            (Timeframe.M15, freshness.m15_candles),
            (Timeframe.H1, freshness.h1_candles),
            (Timeframe.H4, freshness.h4_candles),
        ):
            if observation.state is FreshnessState.STALE:
                warnings.append(
                    SnapshotValidationWarning(
                        code=SnapshotWarningCode.STALE_CANDLE,
                        message="latest completed candle is valid but stale",
                        timeframe=timeframe,
                    )
                )
        if duration > timedelta(seconds=self._settings.slow_snapshot_seconds):
            warnings.append(
                SnapshotValidationWarning(
                    code=SnapshotWarningCode.SLOW_SNAPSHOT,
                    message="snapshot duration exceeded the configured warning threshold",
                )
            )
        if omitted_positions:
            warnings.append(
                SnapshotValidationWarning(
                    code=SnapshotWarningCode.OUT_OF_SCOPE_POSITION_OMITTED,
                    message="positions for other symbols were omitted from this snapshot",
                    omitted_count=omitted_positions,
                )
            )
        return tuple(warnings)

    def _validate_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: tuple[MT5Candle, ...],
        started_at: datetime,
        completed_at: datetime,
        cycle_id: str,
        snapshot_id: str,
    ) -> None:
        previous_open: datetime | None = None
        for candle in candles:
            if candle.symbol != symbol or candle.timeframe is not timeframe:
                raise self._error(
                    MarketDataErrorCategory.INVALID_TIMEFRAME_DATA,
                    "validate_candles",
                    "candle symbol or timeframe does not match its requested collection",
                    cycle_id,
                    snapshot_id,
                    timeframe=timeframe,
                )
            if previous_open is not None and candle.open_time <= previous_open:
                raise self._error(
                    MarketDataErrorCategory.INVALID_TIMEFRAME_DATA,
                    "validate_candles",
                    "candle timestamps must be unique and strictly increasing",
                    cycle_id,
                    snapshot_id,
                    timeframe=timeframe,
                )
            if candle.open_time + timeframe_duration(timeframe) > completed_at:
                raise self._error(
                    MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                    "validate_candles",
                    "incomplete or future candle is not permitted",
                    cycle_id,
                    snapshot_id,
                    timeframe=timeframe,
                )
            self._validate_observation_times(
                started_at,
                completed_at,
                candle.retrieved_at,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
            )
            previous_open = candle.open_time

    def _validate_positions(
        self,
        positions: tuple[MT5OpenPosition, ...],
        started_at: datetime,
        completed_at: datetime,
        cycle_id: str,
        snapshot_id: str,
    ) -> None:
        for position in positions:
            if position.open_time > position.update_time or position.update_time > completed_at:
                raise self._error(
                    MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                    "validate_positions",
                    "position timestamps are inconsistent with the snapshot",
                    cycle_id,
                    snapshot_id,
                )
            self._validate_observation_times(
                started_at,
                completed_at,
                position.retrieved_at,
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
            )

    def _validate_symbol_observations(
        self,
        expected: str,
        symbol_info: str,
        tick: str,
        cycle_id: str,
        snapshot_id: str,
    ) -> None:
        if symbol_info != expected or tick != expected:
            raise self._error(
                MarketDataErrorCategory.MISSING_SYMBOL,
                "validate_symbol",
                "market observations do not match the configured broker symbol",
                cycle_id,
                snapshot_id,
            )

    def _validate_tick_time(
        self,
        source_time: datetime,
        retrieved_at: datetime,
        completed_at: datetime,
        cycle_id: str,
        snapshot_id: str,
    ) -> None:
        if source_time > retrieved_at or source_time > completed_at:
            raise self._error(
                MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                "validate_tick",
                "tick source time is later than its retrieval or snapshot completion",
                cycle_id,
                snapshot_id,
            )

    def _validate_observation_times(
        self,
        started_at: datetime,
        completed_at: datetime,
        *retrieved_at: datetime,
        cycle_id: str,
        snapshot_id: str,
    ) -> None:
        if started_at > completed_at or any(
            value < started_at or value > completed_at for value in retrieved_at
        ):
            raise self._error(
                MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                "validate_retrieval_times",
                "observation retrieval time falls outside the snapshot window",
                cycle_id,
                snapshot_id,
            )

    def _collection_retrieved_at(
        self,
        observations: Sequence[MT5Candle],
        cycle_id: str,
        snapshot_id: str,
    ) -> datetime:
        timestamps = {item.retrieved_at for item in observations}
        if len(timestamps) != 1:
            raise self._error(
                MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                "validate_retrieval_times",
                "one source read produced inconsistent retrieval timestamps",
                cycle_id,
                snapshot_id,
            )
        return next(iter(timestamps))

    def _read_clock(self, cycle_id: str, snapshot_id: str) -> datetime:
        try:
            return normalize_utc(self._clock())
        except ValueError as exc:
            raise self._error(
                MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS,
                "read_clock",
                "snapshot clock must return a timezone-aware timestamp",
                cycle_id,
                snapshot_id,
            ) from exc

    def _error(
        self,
        category: MarketDataErrorCategory,
        operation: str,
        message: str,
        cycle_id: str,
        snapshot_id: str,
        *,
        timeframe: Timeframe | None = None,
        cause_category: str | None = None,
    ) -> MarketDataError:
        self._logger.error(
            "market_snapshot_failed",
            extra={
                "cycle_id": cycle_id,
                "snapshot_id": snapshot_id,
                "operation": operation,
                "error_category": category.value,
                "timeframe": None if timeframe is None else timeframe.value,
                "cause_category": cause_category,
            },
        )
        return MarketDataError(
            category,
            operation,
            message,
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            timeframe=timeframe,
            cause_category=cause_category,
        )
