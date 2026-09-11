"""Immutable deterministic market-feature boundary contracts."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    CycleId,
    FiniteDecimal,
    Identifier,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.enums import (
    DataValidityState,
    FeatureAvailability,
    FeatureUnit,
    FeatureWarningCode,
    Timeframe,
)
from ai_trading_team.schemas.market import SnapshotFreshness


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class DecimalFeatureValue(CoreModel):
    """One numeric feature with explicit availability and history requirements."""

    status: FeatureAvailability
    unit: FeatureUnit
    value: FiniteDecimal | None = None
    required_candles: PositiveInt
    available_candles: NonNegativeInt
    reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.status is FeatureAvailability.VALID:
            if self.value is None or self.available_candles < self.required_candles:
                raise ValueError("valid feature requires a value and sufficient history")
            if self.reason is not None:
                raise ValueError("valid feature must not carry an unavailability reason")
        elif self.status is FeatureAvailability.INSUFFICIENT_HISTORY:
            if self.value is not None or self.available_candles >= self.required_candles:
                raise ValueError("insufficient feature must have no value and too little history")
            if not self.reason:
                raise ValueError("insufficient feature requires a reason")
        else:
            if self.value is not None or self.available_candles < self.required_candles:
                raise ValueError("unavailable feature requires sufficient history and no value")
            if not self.reason:
                raise ValueError("unavailable feature requires a reason")
        return self


class SwingPoint(CoreModel):
    """A confirmed pivot and the time at which its right window became available."""

    price: FiniteDecimal
    candle_open_at: datetime
    confirmed_at: datetime
    left_bars: PositiveInt
    right_bars: PositiveInt

    _normalize_time = field_validator("candle_open_at", "confirmed_at")(_utc)

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        if self.confirmed_at <= self.candle_open_at:
            raise ValueError("swing confirmation must follow the pivot candle open")
        return self


class SwingFeatureValue(CoreModel):
    """Availability wrapper for the most recent confirmed swing point."""

    status: FeatureAvailability
    value: SwingPoint | None = None
    required_candles: PositiveInt
    available_candles: NonNegativeInt
    reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.status is FeatureAvailability.VALID:
            if self.value is None or self.available_candles < self.required_candles:
                raise ValueError("valid swing requires a point and sufficient history")
            if self.reason is not None:
                raise ValueError("valid swing must not carry a reason")
        elif self.status is FeatureAvailability.INSUFFICIENT_HISTORY:
            if self.value is not None or self.available_candles >= self.required_candles:
                raise ValueError("insufficient swing must have no point and too little history")
            if not self.reason:
                raise ValueError("insufficient swing requires a reason")
        else:
            if self.value is not None or self.available_candles < self.required_candles:
                raise ValueError("unavailable swing requires sufficient history and no point")
            if not self.reason:
                raise ValueError("unavailable swing requires a reason")
        return self


class TrendFeatures(CoreModel):
    ema_20: DecimalFeatureValue
    ema_50: DecimalFeatureValue
    ema_200: DecimalFeatureValue
    distance_from_ema_20: DecimalFeatureValue
    distance_from_ema_50: DecimalFeatureValue
    distance_from_ema_200: DecimalFeatureValue

    @model_validator(mode="after")
    def validate_distance_dependencies(self) -> Self:
        for reference, distance in (
            (self.ema_20, self.distance_from_ema_20),
            (self.ema_50, self.distance_from_ema_50),
            (self.ema_200, self.distance_from_ema_200),
        ):
            if (
                distance.status is not reference.status
                or distance.required_candles != reference.required_candles
                or distance.available_candles != reference.available_candles
            ):
                raise ValueError("EMA distance must inherit reference availability and history")
        return self


class MomentumFeatures(CoreModel):
    rsi_14: DecimalFeatureValue


class VolatilityFeatures(CoreModel):
    atr_14: DecimalFeatureValue


class TrendStrengthFeatures(CoreModel):
    adx_14: DecimalFeatureValue


class CandleGeometryFeatures(CoreModel):
    candle_open_at: datetime
    candle_range: DecimalFeatureValue
    real_body: DecimalFeatureValue
    upper_wick: DecimalFeatureValue
    lower_wick: DecimalFeatureValue
    body_range_ratio: DecimalFeatureValue

    _normalize_time = field_validator("candle_open_at")(_utc)


class MarketStructureFeatures(CoreModel):
    recent_swing_high: SwingFeatureValue
    recent_swing_low: SwingFeatureValue
    recent_range_high: DecimalFeatureValue
    recent_range_low: DecimalFeatureValue
    distance_from_recent_swing_high: DecimalFeatureValue
    distance_from_recent_swing_low: DecimalFeatureValue
    distance_from_recent_range_high: DecimalFeatureValue
    distance_from_recent_range_low: DecimalFeatureValue

    @model_validator(mode="after")
    def validate_distance_dependencies(self) -> Self:
        pairs: tuple[
            tuple[SwingFeatureValue | DecimalFeatureValue, DecimalFeatureValue], ...
        ] = (
            (self.recent_swing_high, self.distance_from_recent_swing_high),
            (self.recent_swing_low, self.distance_from_recent_swing_low),
            (self.recent_range_high, self.distance_from_recent_range_high),
            (self.recent_range_low, self.distance_from_recent_range_low),
        )
        for reference, distance in pairs:
            if (
                distance.status is not reference.status
                or distance.required_candles != reference.required_candles
                or distance.available_candles != reference.available_candles
            ):
                raise ValueError("level distance must inherit reference availability and history")
        return self


class FeatureWarning(CoreModel):
    code: FeatureWarningCode
    message: str = Field(max_length=256)
    timeframe: Timeframe | None = None
    feature_names: tuple[Identifier, ...] = ()


class TimeframeFeatureSet(CoreModel):
    timeframe: Timeframe
    source_candle_count: PositiveInt
    source_first_candle_open_at: datetime
    source_last_candle_open_at: datetime
    source_last_candle_close_at: datetime
    evaluation_candle_open_at: datetime
    source_candle_digest: ContentDigest
    validity: Literal[DataValidityState.VALID] = DataValidityState.VALID
    availability: FeatureAvailability
    trend: TrendFeatures
    momentum: MomentumFeatures
    volatility: VolatilityFeatures
    trend_strength: TrendStrengthFeatures
    candle_geometry: CandleGeometryFeatures
    market_structure: MarketStructureFeatures
    warnings: tuple[FeatureWarning, ...] = ()

    _normalize_time = field_validator(
        "source_first_candle_open_at",
        "source_last_candle_open_at",
        "source_last_candle_close_at",
        "evaluation_candle_open_at",
    )(_utc)

    @model_validator(mode="after")
    def validate_source_and_summary(self) -> Self:
        if not (
            self.source_first_candle_open_at
            <= self.source_last_candle_open_at
            < self.source_last_candle_close_at
        ):
            raise ValueError("timeframe source timestamps are inconsistent")
        if self.evaluation_candle_open_at != self.source_last_candle_open_at:
            raise ValueError("features must be evaluated at the latest completed source candle")
        statuses = tuple(item.status for item in self._numeric_features()) + (
            self.market_structure.recent_swing_high.status,
            self.market_structure.recent_swing_low.status,
        )
        expected = (
            FeatureAvailability.INSUFFICIENT_HISTORY
            if FeatureAvailability.INSUFFICIENT_HISTORY in statuses
            else FeatureAvailability.UNAVAILABLE
            if FeatureAvailability.UNAVAILABLE in statuses
            else FeatureAvailability.VALID
        )
        if self.availability is not expected:
            raise ValueError("timeframe availability must summarize its feature values")
        return self

    def _numeric_features(self) -> tuple[DecimalFeatureValue, ...]:
        return (
            self.trend.ema_20,
            self.trend.ema_50,
            self.trend.ema_200,
            self.trend.distance_from_ema_20,
            self.trend.distance_from_ema_50,
            self.trend.distance_from_ema_200,
            self.momentum.rsi_14,
            self.volatility.atr_14,
            self.trend_strength.adx_14,
            self.candle_geometry.candle_range,
            self.candle_geometry.real_body,
            self.candle_geometry.upper_wick,
            self.candle_geometry.lower_wick,
            self.candle_geometry.body_range_ratio,
            self.market_structure.recent_range_high,
            self.market_structure.recent_range_low,
            self.market_structure.distance_from_recent_swing_high,
            self.market_structure.distance_from_recent_swing_low,
            self.market_structure.distance_from_recent_range_high,
            self.market_structure.distance_from_recent_range_low,
        )


class TimeframeFeatureCollection(CoreModel):
    m15: TimeframeFeatureSet
    h1: TimeframeFeatureSet
    h4: TimeframeFeatureSet

    @model_validator(mode="after")
    def validate_timeframes(self) -> Self:
        if (
            self.m15.timeframe is not Timeframe.M15
            or self.h1.timeframe is not Timeframe.H1
            or self.h4.timeframe is not Timeframe.H4
        ):
            raise ValueError("feature collection must contain M15, H1, and H4 in fixed fields")
        return self


class SourceCandleDigests(CoreModel):
    m15: ContentDigest
    h1: ContentDigest
    h4: ContentDigest


class FeatureDefinitionVersions(CoreModel):
    ema: SchemaVersion
    rsi: SchemaVersion
    atr: SchemaVersion
    adx: SchemaVersion
    candle_geometry: SchemaVersion
    confirmed_swing: SchemaVersion
    recent_range: SchemaVersion
    signed_distance: SchemaVersion


class FeatureProvenance(CoreModel):
    canonicalization_version: SchemaVersion
    source_snapshot_schema_version: SchemaVersion
    source_snapshot_completed_at: datetime
    feature_engine_version: SchemaVersion
    feature_set_version: SchemaVersion
    configuration_version: SchemaVersion
    configuration_digest: ContentDigest
    source_candle_digests: SourceCandleDigests
    definition_versions: FeatureDefinitionVersions
    decimal_precision: PositiveInt
    decimal_rounding: Literal["ROUND_HALF_EVEN"] = "ROUND_HALF_EVEN"
    completed_candles_only: Literal[True] = True

    _normalize_time = field_validator("source_snapshot_completed_at")(_utc)


class MarketFeatureSet(CoreModel):
    """Deterministic facts derived exclusively from one accepted M2 snapshot."""

    schema_version: SchemaVersion = "1.0.0"
    feature_set_version: SchemaVersion
    feature_engine_version: SchemaVersion
    cycle_id: CycleId
    snapshot_id: SnapshotId
    symbol: Symbol
    primary_timeframe: Timeframe
    generated_at: datetime
    source_validity: Literal[DataValidityState.VALID] = DataValidityState.VALID
    source_freshness: SnapshotFreshness
    timeframes: TimeframeFeatureCollection
    warnings: tuple[FeatureWarning, ...] = ()
    provenance: FeatureProvenance

    _normalize_time = field_validator("generated_at")(_utc)

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        if (
            self.generated_at != self.provenance.source_snapshot_completed_at
            or self.feature_set_version != self.provenance.feature_set_version
            or self.feature_engine_version != self.provenance.feature_engine_version
        ):
            raise ValueError("feature-set identity must match provenance")
        if (
            self.timeframes.m15.source_candle_digest
            != self.provenance.source_candle_digests.m15
            or self.timeframes.h1.source_candle_digest
            != self.provenance.source_candle_digests.h1
            or self.timeframes.h4.source_candle_digest
            != self.provenance.source_candle_digests.h4
        ):
            raise ValueError("timeframe source digests must match provenance")
        if any(
            item.source_last_candle_close_at > self.generated_at
            for item in (self.timeframes.m15, self.timeframes.h1, self.timeframes.h4)
        ):
            raise ValueError("feature source must not extend beyond generation time")
        return self
