"""Immutable M8 historical-data boundary contracts."""

from datetime import UTC, datetime
from typing import Self

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    FiniteDecimal,
    Identifier,
    SchemaVersion,
    Symbol,
)
from ai_trading_team.schemas.enums import DatasetPartitionKind, Timeframe
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5Tick,
)
from ai_trading_team.schemas.timeframes import timeframe_duration


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class DatasetPartition(CoreModel):
    """Explicit context and scored-evaluation ranges for one partition."""

    partition_id: Identifier
    kind: DatasetPartitionKind
    context_start: datetime
    evaluation_start: datetime
    evaluation_end: datetime

    _normalize_time = field_validator(
        "context_start", "evaluation_start", "evaluation_end"
    )(_utc)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if not self.context_start <= self.evaluation_start < self.evaluation_end:
            raise ValueError(
                "partition requires context_start <= evaluation_start < evaluation_end"
            )
        return self


class HistoricalDatasetMetadata(CoreModel):
    """Non-secret identity and coverage included in the dataset digest."""

    schema_version: SchemaVersion = "1.0.0"
    dataset_id: Identifier
    dataset_version: SchemaVersion
    source_ref: Identifier
    symbols: tuple[Symbol, ...] = Field(min_length=1)
    timeframes: tuple[Timeframe, ...] = Field(min_length=1)
    partitions: tuple[DatasetPartition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_identity(self) -> Self:
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("dataset symbols must be unique")
        if len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError("dataset timeframes must be unique")
        ids = tuple(item.partition_id for item in self.partitions)
        if len(set(ids)) != len(ids):
            raise ValueError("dataset partition identifiers must be unique")
        ordered = sorted(self.partitions, key=lambda item: item.evaluation_start)
        if any(
            previous.evaluation_end > current.evaluation_start
            for previous, current in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("dataset evaluation ranges must not overlap")
        return self


class HistoricalCandle(CoreModel):
    """One source candle with optional metadata represented without invention."""

    schema_version: SchemaVersion = "1.0.0"
    source_record_id: Identifier
    symbol: Symbol
    timeframe: Timeframe
    open_time: datetime
    open: FiniteDecimal
    high: FiniteDecimal
    low: FiniteDecimal
    close: FiniteDecimal
    tick_volume: NonNegativeInt | None = None
    broker_spread_points: NonNegativeInt | None = None
    real_volume: NonNegativeInt | None = None

    _normalize_time = field_validator("open_time")(_utc)

    @model_validator(mode="after")
    def validate_candle(self) -> Self:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("historical high/low must contain open and close")
        if self.high < self.low:
            raise ValueError("historical candle high must not be below low")
        return self

    @property
    def close_time(self) -> datetime:
        return self.open_time + timeframe_duration(self.timeframe)


class HistoricalSnapshotObservations(CoreModel):
    """Complete as-of observations required to reproduce an exact M2 snapshot."""

    schema_version: SchemaVersion = "1.0.0"
    observation_id: Identifier
    effective_at: datetime
    symbol: Symbol
    symbol_info: MT5SymbolInfo
    tick: MT5Tick
    account: MT5AccountInfo
    open_positions: tuple[MT5OpenPosition, ...] = ()

    _normalize_time = field_validator("effective_at")(_utc)

    @model_validator(mode="after")
    def validate_observations(self) -> Self:
        if self.symbol_info.symbol != self.symbol or self.tick.symbol != self.symbol:
            raise ValueError("historical observations must match their symbol")
        if self.tick.source_time > self.effective_at:
            raise ValueError("historical tick source time must not follow effective_at")
        if any(
            observed_at > self.effective_at
            for observed_at in (
                self.symbol_info.retrieved_at,
                self.tick.retrieved_at,
                self.account.retrieved_at,
                *(position.retrieved_at for position in self.open_positions),
            )
        ):
            raise ValueError("historical observation retrieval must not follow effective_at")
        if any(
            position.symbol != self.symbol or position.update_time > self.effective_at
            for position in self.open_positions
        ):
            raise ValueError("historical positions must match symbol and as-of time")
        return self


class HistoricalDataset(CoreModel):
    """Sealed deterministic dataset; its digest is verified by the source adapter."""

    schema_version: SchemaVersion = "1.0.0"
    metadata: HistoricalDatasetMetadata
    dataset_digest: ContentDigest
    candles: tuple[HistoricalCandle, ...] = Field(min_length=1)
    snapshot_observations: tuple[HistoricalSnapshotObservations, ...] = ()

    @model_validator(mode="after")
    def validate_membership_and_order(self) -> Self:
        symbols = set(self.metadata.symbols)
        timeframes = set(self.metadata.timeframes)
        keys: list[tuple[str, str, datetime]] = []
        record_ids: list[str] = []
        for candle in self.candles:
            if candle.symbol not in symbols or candle.timeframe not in timeframes:
                raise ValueError("historical candle is outside declared dataset identity")
            keys.append((candle.symbol, candle.timeframe.value, candle.open_time))
            record_ids.append(candle.source_record_id)
        if keys != sorted(keys):
            raise ValueError("historical candles must use canonical identity/time order")
        if len(set(keys)) != len(keys):
            raise ValueError("historical candle symbol/timeframe/open-time keys must be unique")
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("historical candle source record identifiers must be unique")
        observation_keys = [
            (item.symbol, item.effective_at)
            for item in self.snapshot_observations
        ]
        if observation_keys != sorted(observation_keys):
            raise ValueError("historical observations must use canonical symbol/time order")
        if len(set(observation_keys)) != len(observation_keys):
            raise ValueError("historical observation symbol/effective-time keys must be unique")
        observation_ids = [item.observation_id for item in self.snapshot_observations]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("historical observation identifiers must be unique")
        return self
