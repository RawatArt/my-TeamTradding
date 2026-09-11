"""Immutable M8 replay-frame and frozen-decision contracts."""

from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import Field, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    CycleId,
    Identifier,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    EntryActivationPolicy,
    IntrabarPolicy,
    OutcomeBasis,
    ReplayDecisionSource,
    Timeframe,
)
from ai_trading_team.schemas.features import MarketFeatureSet
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import RiskDecision


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class OutcomeHorizon(CoreModel):
    """Exactly one finite future-data bound."""

    max_bars: PositiveInt | None = Field(default=100, le=10_000)
    max_elapsed: timedelta | None = Field(default=None, gt=timedelta(0), le=timedelta(days=365))

    @model_validator(mode="after")
    def validate_exactly_one_bound(self) -> Self:
        if (self.max_bars is None) == (self.max_elapsed is None):
            raise ValueError("outcome horizon requires exactly one finite bound")
        return self


class ReplayConfiguration(CoreModel):
    """Complete deterministic choices for one offline replay."""

    schema_version: SchemaVersion = "1.0.0"
    configuration_version: Literal["1.0.0"] = "1.0.0"
    dataset_id: Identifier
    dataset_digest: ContentDigest
    partition_id: Identifier
    symbol: Symbol
    primary_timeframe: Timeframe = Timeframe.M15
    m15_candle_count: PositiveInt = Field(default=200, le=5_000)
    h1_candle_count: PositiveInt = Field(default=200, le=5_000)
    h4_candle_count: PositiveInt = Field(default=200, le=5_000)
    replay_schedule: tuple[datetime, ...] = Field(min_length=1)
    feature_configuration_digest: ContentDigest
    outcome_timeframe: Timeframe = Timeframe.M15
    outcome_horizon: OutcomeHorizon = Field(default_factory=OutcomeHorizon)
    entry_policy: Literal[EntryActivationPolicy.ACTIVE_AT_DECISION_CUTOFF] = (
        EntryActivationPolicy.ACTIVE_AT_DECISION_CUTOFF
    )
    intrabar_policy: Literal[IntrabarPolicy.MARK_AMBIGUOUS] = IntrabarPolicy.MARK_AMBIGUOUS
    outcome_basis: Literal[OutcomeBasis.THEORETICAL_LEVEL_TOUCH_NO_COSTS] = (
        OutcomeBasis.THEORETICAL_LEVEL_TOUCH_NO_COSTS
    )
    evaluation_policy_version: Literal["1.0.0"] = "1.0.0"
    segmentation_policy_digest: ContentDigest | None = None

    _normalize_schedule = field_validator("replay_schedule")(
        lambda values: tuple(_utc(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if tuple(sorted(set(self.replay_schedule))) != self.replay_schedule:
            raise ValueError("replay schedule must be unique and strictly increasing")
        return self


class ArtifactReference(CoreModel):
    """Content-addressed reference without embedding a full sensitive artifact."""

    artifact_id: Identifier
    schema_version: SchemaVersion
    digest: ContentDigest


class ReplayFrame(CoreModel):
    """Decision-world artifact that is structurally incapable of carrying outcomes."""

    schema_version: SchemaVersion = "1.0.0"
    replay_id: Identifier
    frame_id: Identifier
    dataset_id: Identifier
    dataset_digest: ContentDigest
    partition_id: Identifier
    partition_kind: DatasetPartitionKind
    cycle_id: CycleId
    snapshot_id: SnapshotId
    symbol: Symbol
    primary_timeframe: Timeframe
    replay_time: datetime
    decision_cutoff: datetime
    market_snapshot: ArtifactReference
    market_features: ArtifactReference
    replay_configuration_digest: ContentDigest
    generated_at: datetime

    _normalize_time = field_validator("replay_time", "decision_cutoff", "generated_at")(_utc)

    @model_validator(mode="after")
    def validate_frame(self) -> Self:
        if self.decision_cutoff > self.replay_time:
            raise ValueError("decision cutoff must not follow replay time")
        if self.generated_at != self.replay_time:
            raise ValueError("frame generation time must equal deterministic replay time")
        return self


class ReplayBuildResult(CoreModel):
    """In-memory decision artifacts; only sanitized references require persistence."""

    frame: ReplayFrame
    snapshot: MarketSnapshot
    features: MarketFeatureSet

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        from ai_trading_team.replay.serialization import content_digest

        frame = self.frame
        if (
            self.snapshot.cycle_id != frame.cycle_id
            or self.snapshot.snapshot_id != frame.snapshot_id
            or self.features.cycle_id != frame.cycle_id
            or self.features.snapshot_id != frame.snapshot_id
            or self.snapshot.symbol != frame.symbol
            or self.features.symbol != frame.symbol
        ):
            raise ValueError("replay build artifacts must share frame trace identity")
        if (
            frame.market_snapshot.digest != content_digest(self.snapshot)
            or frame.market_features.digest != content_digest(self.features)
        ):
            raise ValueError("replay frame artifact digests must match exact decision artifacts")
        return self


class PersistedRiskDecisionLink(CoreModel):
    """Exact linkage proving which frozen proposal an historical Risk decision evaluated."""

    schema_version: SchemaVersion = "1.0.0"
    proposal_digest: ContentDigest
    risk_decision_digest: ContentDigest
    risk_decision: RiskDecision


class FrozenReplayDecision(CoreModel):
    """Immutable proposal gate that must exist before outcome data can be requested."""

    schema_version: SchemaVersion = "1.0.0"
    frozen_decision_id: Identifier
    replay_id: Identifier
    frame_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    symbol: Symbol
    decision_cutoff: datetime
    frozen_at: datetime
    source: ReplayDecisionSource
    proposal: TradeProposal
    proposal_digest: ContentDigest
    entry_policy: Literal[EntryActivationPolicy.ACTIVE_AT_DECISION_CUTOFF] = (
        EntryActivationPolicy.ACTIVE_AT_DECISION_CUTOFF
    )
    risk_link: PersistedRiskDecisionLink | None = None

    _normalize_time = field_validator("decision_cutoff", "frozen_at")(_utc)

    @model_validator(mode="after")
    def validate_linkage(self) -> Self:
        from ai_trading_team.replay.serialization import content_digest

        proposal = self.proposal
        if self.frozen_at < self.decision_cutoff:
            raise ValueError("decision cannot be frozen before its decision cutoff")
        if (
            proposal.cycle_id != self.cycle_id
            or proposal.snapshot_id != self.snapshot_id
            or proposal.symbol != self.symbol
        ):
            raise ValueError("frozen proposal must match replay trace and symbol")
        if proposal.schema_version != "1.0.0":
            raise ValueError("frozen proposal schema version is unsupported")
        if self.proposal_digest != content_digest(proposal):
            raise ValueError("frozen proposal digest must match exact proposal content")
        if self.risk_link is not None:
            risk = self.risk_link.risk_decision
            if self.risk_link.proposal_digest != self.proposal_digest:
                raise ValueError("Risk linkage proposal digest must match frozen proposal")
            if (
                risk.schema_version != "1.0.0"
                or risk.cycle_id != self.cycle_id
                or risk.snapshot_id != self.snapshot_id
                or risk.proposal_id != proposal.proposal_id
                or risk.symbol != self.symbol
            ):
                raise ValueError("persisted Risk decision is incompatible with frozen proposal")
            if self.risk_link.risk_decision_digest != content_digest(risk):
                raise ValueError("persisted Risk decision digest must match exact decision content")
        return self
