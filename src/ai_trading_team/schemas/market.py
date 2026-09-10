"""Strict market-data boundary contracts."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    CoreModel,
    CycleId,
    NonNegativeDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
    TraceableRecord,
)
from ai_trading_team.schemas.enums import (
    DataValidityState,
    FreshnessState,
    SnapshotWarningCode,
    Timeframe,
)
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5Candle,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5Tick,
)
from ai_trading_team.schemas.timeframes import timeframe_duration


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class MarketQuote(TraceableRecord):
    """A validated bid/ask quote; full MarketSnapshot belongs to M2."""

    symbol: Symbol
    timeframe: Timeframe
    bid: NonNegativeDecimal
    ask: NonNegativeDecimal
    spread: NonNegativeDecimal

    @model_validator(mode="after")
    def validate_price_relationships(self) -> "MarketQuote":
        """Ensure ask and declared spread agree exactly in decimal arithmetic."""
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        expected_spread = self.ask - self.bid
        if self.spread != expected_spread:
            raise ValueError("spread must equal ask minus bid")
        return self

    @property
    def mid(self) -> Decimal:
        """Return the exact decimal midpoint without binary float conversion."""
        return (self.bid + self.ask) / Decimal("2")


class SnapshotCandles(CoreModel):
    """Completed candle histories required by every M2 snapshot."""

    m15: tuple[MT5Candle, ...] = Field(min_length=1)
    h1: tuple[MT5Candle, ...] = Field(min_length=1)
    h4: tuple[MT5Candle, ...] = Field(min_length=1)


class SnapshotSourceTimestamps(CoreModel):
    """Retrieval timestamps proving each source was read inside one build window."""

    symbol_info: datetime
    account: datetime
    m15_candles: datetime
    h1_candles: datetime
    h4_candles: datetime
    positions: datetime
    tick: datetime

    _normalize_utc = field_validator("*")(_utc)


class ObservationFreshness(CoreModel):
    """Age classification for one valid observation at snapshot completion."""

    observed_at: datetime
    evaluated_at: datetime
    age: timedelta
    maximum_age: timedelta
    state: FreshnessState

    _normalize_utc = field_validator("observed_at", "evaluated_at")(_utc)

    @model_validator(mode="after")
    def validate_freshness(self) -> "ObservationFreshness":
        if self.age < timedelta(0) or self.maximum_age <= timedelta(0):
            raise ValueError("freshness durations must be non-negative with a positive maximum")
        if self.age != self.evaluated_at - self.observed_at:
            raise ValueError("freshness age must equal evaluated_at minus observed_at")
        expected = (
            FreshnessState.FRESH if self.age <= self.maximum_age else FreshnessState.STALE
        )
        if self.state is not expected:
            raise ValueError("freshness state does not match the configured maximum age")
        return self


class SnapshotFreshness(CoreModel):
    """Freshness is descriptive and does not imply M2 tradeability."""

    tick: ObservationFreshness
    account: ObservationFreshness
    m15_candles: ObservationFreshness
    h1_candles: ObservationFreshness
    h4_candles: ObservationFreshness
    overall: FreshnessState

    @model_validator(mode="after")
    def validate_overall_state(self) -> "SnapshotFreshness":
        observations = (
            self.tick,
            self.account,
            self.m15_candles,
            self.h1_candles,
            self.h4_candles,
        )
        expected = (
            FreshnessState.STALE
            if any(item.state is FreshnessState.STALE for item in observations)
            else FreshnessState.FRESH
        )
        if self.overall is not expected:
            raise ValueError("overall freshness must summarize all observation freshness states")
        return self


class SnapshotValidationWarning(CoreModel):
    """Typed non-fatal finding retained with a valid snapshot."""

    code: SnapshotWarningCode
    message: str
    timeframe: Timeframe | None = None
    omitted_count: NonNegativeInt | None = None


class SnapshotConsistencyMetadata(CoreModel):
    """Validity, retrieval timing, duration, freshness, and non-fatal findings."""

    validity: Literal[DataValidityState.VALID] = DataValidityState.VALID
    source_timestamps: SnapshotSourceTimestamps
    snapshot_duration: timedelta
    freshness: SnapshotFreshness
    validation_warnings: tuple[SnapshotValidationWarning, ...] = ()

    @field_validator("snapshot_duration")
    @classmethod
    def require_non_negative_duration(cls, value: timedelta) -> timedelta:
        if value < timedelta(0):
            raise ValueError("snapshot_duration must not be negative")
        return value


class MarketSnapshot(CoreModel):
    """One valid immutable market capture owned by one explicit decision cycle."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    symbol: Symbol
    primary_timeframe: Timeframe
    snapshot_started_at: datetime
    snapshot_completed_at: datetime
    symbol_info: MT5SymbolInfo
    tick: MT5Tick
    spread: NonNegativeDecimal
    candles: SnapshotCandles
    account: MT5AccountInfo
    open_positions: tuple[MT5OpenPosition, ...]
    consistency: SnapshotConsistencyMetadata

    _normalize_utc = field_validator("snapshot_started_at", "snapshot_completed_at")(_utc)

    @model_validator(mode="after")
    def validate_aggregate(self) -> "MarketSnapshot":
        if self.snapshot_started_at > self.snapshot_completed_at:
            raise ValueError("snapshot start must not be after completion")
        if self.consistency.snapshot_duration != (
            self.snapshot_completed_at - self.snapshot_started_at
        ):
            raise ValueError("snapshot duration must match the snapshot window")
        if self.symbol_info.symbol != self.symbol or self.tick.symbol != self.symbol:
            raise ValueError("snapshot observations must match the snapshot symbol")
        if self.spread != self.tick.spread or self.spread != self.tick.ask - self.tick.bid:
            raise ValueError("snapshot spread must exactly match its tick")
        if any(position.symbol != self.symbol for position in self.open_positions):
            raise ValueError("snapshot positions must be scoped to the snapshot symbol")

        source = self.consistency.source_timestamps
        source_times = source.model_dump(mode="python").values()
        if any(
            value < self.snapshot_started_at or value > self.snapshot_completed_at
            for value in source_times
        ):
            raise ValueError("source retrieval timestamp falls outside the snapshot window")
        if self.tick.source_time > self.tick.retrieved_at:
            raise ValueError("tick source time must not be later than retrieval time")
        if (
            source.symbol_info != self.symbol_info.retrieved_at
            or source.account != self.account.retrieved_at
            or source.tick != self.tick.retrieved_at
        ):
            raise ValueError("source timestamps must match their observations")
        if any(
            position.open_time > position.update_time
            or position.update_time > self.snapshot_completed_at
            or position.retrieved_at > source.positions
            for position in self.open_positions
        ):
            raise ValueError("position timestamps must be consistent with snapshot completion")

        collections = (
            (Timeframe.M15, self.candles.m15, source.m15_candles),
            (Timeframe.H1, self.candles.h1, source.h1_candles),
            (Timeframe.H4, self.candles.h4, source.h4_candles),
        )
        freshness = self.consistency.freshness
        freshness_by_timeframe = {
            Timeframe.M15: freshness.m15_candles,
            Timeframe.H1: freshness.h1_candles,
            Timeframe.H4: freshness.h4_candles,
        }
        for timeframe, candles, source_time in collections:
            previous_open: datetime | None = None
            for candle in candles:
                if (
                    candle.retrieved_at < self.snapshot_started_at
                    or candle.retrieved_at > self.snapshot_completed_at
                ):
                    raise ValueError("candle retrieval time falls outside the snapshot window")
                if candle.symbol != self.symbol or candle.timeframe is not timeframe:
                    raise ValueError("candle symbol or timeframe does not match its collection")
                if candle.retrieved_at != source_time:
                    raise ValueError("candle retrieval times must match their source timestamp")
                if previous_open is not None and candle.open_time <= previous_open:
                    raise ValueError("candle opening times must be unique and strictly increasing")
                if candle.open_time + timeframe_duration(timeframe) > self.snapshot_completed_at:
                    raise ValueError("snapshot cannot contain an incomplete or future candle")
                previous_open = candle.open_time

            candle_freshness = freshness_by_timeframe[timeframe]
            latest_close = candles[-1].open_time + timeframe_duration(timeframe)
            if candle_freshness.observed_at != latest_close:
                raise ValueError("candle freshness must refer to the latest completed candle")

        if freshness.tick.observed_at != self.tick.source_time:
            raise ValueError("tick freshness must refer to tick source time")
        if freshness.account.observed_at != self.account.retrieved_at:
            raise ValueError("account freshness must refer to account retrieval time")
        if any(
            item.evaluated_at != self.snapshot_completed_at
            for item in (
                freshness.tick,
                freshness.account,
                freshness.m15_candles,
                freshness.h1_candles,
                freshness.h4_candles,
            )
        ):
            raise ValueError("all freshness values must be evaluated at snapshot completion")
        return self
