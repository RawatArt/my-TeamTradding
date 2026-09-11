"""Immutable M8 outcome and research-metric contracts."""

from datetime import UTC, datetime
from decimal import Context, localcontext
from typing import Self

from pydantic import NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    CycleId,
    FiniteDecimal,
    Identifier,
    NonNegativeDecimal,
    PositiveDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    OutcomeBasis,
    ResearchMetricStatus,
    SegmentDimension,
    Timeframe,
    TradeOutcomeStatus,
    TradeSide,
)
from ai_trading_team.schemas.replay import OutcomeHorizon
from ai_trading_team.schemas.timeframes import timeframe_duration


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


class SegmentFacts(CoreModel):
    """Only pre-outcome immutable facts allowed in descriptive segmentation."""

    direction: TradeSide
    timeframe: Timeframe
    partition: DatasetPartitionKind
    feature_regime: Identifier | None = None
    volatility_bucket: Identifier | None = None
    trend_strength_bucket: Identifier | None = None
    chief_decision: Identifier | None = None
    skeptic_decision: Identifier | None = None


class TradeOutcome(CoreModel):
    """Finite theoretical price-path result for one frozen proposal."""

    schema_version: SchemaVersion = "1.0.0"
    evaluator_version: SchemaVersion = "1.0.0"
    outcome_id: Identifier
    replay_id: Identifier
    frame_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    proposal_id: Identifier
    proposal_digest: ContentDigest
    dataset_id: Identifier
    dataset_digest: ContentDigest
    partition_id: Identifier
    partition_kind: DatasetPartitionKind
    symbol: Symbol
    side: TradeSide
    timeframe: Timeframe
    decision_cutoff: datetime
    evaluation_started_at: datetime
    evaluation_ended_at: datetime
    horizon: OutcomeHorizon
    bars_evaluated: NonNegativeInt
    status: TradeOutcomeStatus
    resolution_candle_open_at: datetime | None = None
    resolution_candle_close_at: datetime | None = None
    bars_to_resolution: NonNegativeInt | None = None
    seconds_to_resolution: NonNegativeDecimal | None = None
    entry: FiniteDecimal
    stop_loss: FiniteDecimal
    take_profit: FiniteDecimal
    risk_unit: PositiveDecimal
    realized_r_multiple: FiniteDecimal | None = None
    maximum_favorable_excursion: NonNegativeDecimal
    maximum_adverse_excursion: NonNegativeDecimal
    mfe_r: NonNegativeDecimal
    mae_r: NonNegativeDecimal
    outcome_candle_digest: ContentDigest
    evaluation_policy_digest: ContentDigest
    outcome_basis: OutcomeBasis
    segment_facts: SegmentFacts

    _normalize_time = field_validator(
        "decision_cutoff",
        "evaluation_started_at",
        "evaluation_ended_at",
    )(_utc)
    _normalize_optional_time = field_validator(
        "resolution_candle_open_at", "resolution_candle_close_at"
    )(_optional_utc)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.evaluation_started_at < self.decision_cutoff:
            raise ValueError("outcome evaluation must start in the post-decision interval")
        if self.evaluation_ended_at < self.evaluation_started_at or self.bars_evaluated < 1:
            raise ValueError("outcome requires a non-empty chronological finite window")
        valid_geometry = (
            self.stop_loss < self.entry < self.take_profit
            if self.side is TradeSide.BUY
            else self.take_profit < self.entry < self.stop_loss
        )
        if not valid_geometry or self.risk_unit != abs(self.entry - self.stop_loss):
            raise ValueError("outcome prices and risk unit must preserve proposal geometry")
        with localcontext(Context(prec=50)):
            if self.mfe_r != self.maximum_favorable_excursion / self.risk_unit:
                raise ValueError("MFE R must match price excursion and risk unit")
            if self.mae_r != self.maximum_adverse_excursion / self.risk_unit:
                raise ValueError("MAE R must match price excursion and risk unit")
        resolved = self.status in {
            TradeOutcomeStatus.TAKE_PROFIT_REACHED,
            TradeOutcomeStatus.STOP_LOSS_REACHED,
        }
        terminal_candle = resolved or self.status is TradeOutcomeStatus.AMBIGUOUS_INTRABAR
        fields_present = all(
            value is not None
            for value in (
                self.resolution_candle_open_at,
                self.resolution_candle_close_at,
                self.bars_to_resolution,
                self.seconds_to_resolution,
            )
        )
        if terminal_candle != fields_present:
            raise ValueError("terminal candle metadata must match outcome status")
        if resolved != (self.realized_r_multiple is not None):
            raise ValueError("only unambiguous resolved outcomes have realized R")
        if self.status is TradeOutcomeStatus.STOP_LOSS_REACHED and self.realized_r_multiple != -1:
            raise ValueError("stop-loss outcome must equal negative one R")
        if self.status is TradeOutcomeStatus.TAKE_PROFIT_REACHED:
            with localcontext(Context(prec=50)):
                expected_r = abs(self.take_profit - self.entry) / self.risk_unit
            if self.realized_r_multiple != expected_r:
                raise ValueError("take-profit R must match the frozen target geometry")
        if terminal_candle and (
            self.resolution_candle_open_at is None
            or self.resolution_candle_close_at is None
            or self.resolution_candle_close_at
            != self.resolution_candle_open_at + timeframe_duration(self.timeframe)
            or self.resolution_candle_close_at != self.evaluation_ended_at
            or self.bars_to_resolution != self.bars_evaluated
        ):
            raise ValueError("resolution metadata must identify the terminal candle")
        return self


class ResearchMetric(CoreModel):
    """Finite metric or an explicit unavailable/unbounded state."""

    status: ResearchMetricStatus
    value: FiniteDecimal | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if (self.status is ResearchMetricStatus.VALID) != (self.value is not None):
            raise ValueError("only a valid research metric carries a finite value")
        return self


class PerformanceSummary(CoreModel):
    """Deterministic R-based outcome sequence summary, not an equity simulation."""

    schema_version: SchemaVersion = "1.0.0"
    summary_id: Identifier
    replay_id: Identifier
    dataset_digest: ContentDigest
    partition_id: Identifier
    partition_kind: DatasetPartitionKind
    outcome_count: NonNegativeInt
    resolved_count: NonNegativeInt
    unresolved_count: NonNegativeInt
    ambiguous_count: NonNegativeInt
    win_count: NonNegativeInt
    loss_count: NonNegativeInt
    win_rate: ResearchMetric
    cumulative_r: ResearchMetric
    average_r: ResearchMetric
    median_r: ResearchMetric
    expectancy_r: ResearchMetric
    profit_factor: ResearchMetric
    sequence_max_drawdown_r: ResearchMetric
    average_holding_bars: ResearchMetric
    average_holding_seconds: ResearchMetric
    average_mfe_r: ResearchMetric
    average_mae_r: ResearchMetric
    outcome_digest: ContentDigest
    metrics_version: SchemaVersion = "1.0.0"
    generated_at: datetime

    _normalize_time = field_validator("generated_at")(_utc)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.outcome_count != self.resolved_count + self.unresolved_count + self.ambiguous_count:
            raise ValueError("outcome counts must partition the complete result set")
        if self.resolved_count != self.win_count + self.loss_count:
            raise ValueError("resolved count must equal wins plus losses")
        return self


class SegmentedPerformanceSummary(CoreModel):
    """One descriptive group selected from pre-outcome facts."""

    dimension: SegmentDimension
    value: Identifier
    summary: PerformanceSummary
