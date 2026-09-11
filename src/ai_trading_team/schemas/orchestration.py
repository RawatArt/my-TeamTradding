"""M4 role-input, failure, stage, debate, and retrospective contracts."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.agents import (
    AgentEvidence,
    AgentMarketView,
    ChiefTraderOutput,
    EntryAnalysisOutput,
    MarketContextOutput,
    PriceActionOutput,
    QuantDeveloperOutput,
    QuantResearchOutput,
    SkepticOutput,
    TrendAnalysisOutput,
)
from ai_trading_team.schemas.common import CoreModel, CycleId, Identifier, SchemaVersion, SnapshotId
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentFailureCategory,
    AgentRole,
    FailureDisposition,
    PipelineComponent,
    PipelineKind,
)
from ai_trading_team.schemas.risk import RiskDecision


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _validate_output_trace(
    cycle_id: str,
    snapshot_id: str,
    outputs: tuple[object | None, ...],
) -> None:
    for output in outputs:
        if output is None:
            continue
        output_cycle = getattr(output, "cycle_id", None)
        output_snapshot = getattr(output, "snapshot_id", None)
        if output_cycle != cycle_id or output_snapshot != snapshot_id:
            raise ValueError("upstream output must match input cycle and snapshot")


def _stage_one_records(context: "StageOneContext") -> tuple[object | None, ...]:
    return (
        context.market_context,
        context.trend,
        context.price_action,
        *context.failures,
    )


class AgentFailureRecord(CoreModel):
    """An observed failure; it is never presented as a fabricated agent output."""

    schema_version: SchemaVersion = "1.0.0"
    failure_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    agent_role: AgentRole | None = None
    execution_profile: AgentExecutionProfile | None = None
    category: AgentFailureCategory
    occurred_at: datetime
    sanitized_detail: str = Field(min_length=1, max_length=512)
    disposition: FailureDisposition

    _normalize_time = field_validator("occurred_at")(_utc)

    @model_validator(mode="after")
    def require_role_for_agent_failures(self) -> Self:
        input_categories = {
            AgentFailureCategory.STALE_SNAPSHOT,
            AgentFailureCategory.INVALID_SNAPSHOT,
            AgentFailureCategory.SCHEMA_MISMATCH,
            AgentFailureCategory.UNKNOWN,
        }
        if self.category not in input_categories and self.agent_role is None:
            raise ValueError("agent failure category requires an agent role")
        return self


class SnapshotAgentInput(CoreModel):
    """Common trace and sanitized snapshot view for decision-cycle roles."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    market: AgentMarketView

    @model_validator(mode="after")
    def validate_market_trace(self) -> Self:
        if self.market.cycle_id != self.cycle_id or self.market.snapshot_id != self.snapshot_id:
            raise ValueError("market view must match input cycle and snapshot")
        return self


class MarketContextInput(SnapshotAgentInput):
    """Market Context sees only the sanitized current market view."""


class TrendAnalysisInput(SnapshotAgentInput):
    """Trend Analyst sees only the sanitized current market view."""


class PriceActionInput(SnapshotAgentInput):
    """Price Action Analyst sees only the sanitized current market view."""


class StageOneContext(CoreModel):
    """Typed parallel outputs and failures from Stage 1."""

    market_context: MarketContextOutput | None = None
    trend: TrendAnalysisOutput | None = None
    price_action: PriceActionOutput | None = None
    failures: tuple[AgentFailureRecord, ...] = ()

    @property
    def successful_output_count(self) -> int:
        outputs = (self.market_context, self.trend, self.price_action)
        return sum(item is not None for item in outputs)


class EntryAnalysisInput(SnapshotAgentInput):
    stage_one: StageOneContext

    @model_validator(mode="after")
    def validate_upstream_trace(self) -> Self:
        _validate_output_trace(
            self.cycle_id,
            self.snapshot_id,
            _stage_one_records(self.stage_one),
        )
        return self


class PerformanceHistoryReference(CoreModel):
    """Read-only pointer to future analytical history; M4 resolves no storage."""

    history_id: Identifier
    schema_version: SchemaVersion
    as_of: datetime
    record_count: NonNegativeInt

    _normalize_time = field_validator("as_of")(_utc)


class QuantResearchInput(SnapshotAgentInput):
    stage_one: StageOneContext
    entry: EntryAnalysisOutput
    performance_history: PerformanceHistoryReference | None = None

    @model_validator(mode="after")
    def validate_upstream_trace(self) -> Self:
        _validate_output_trace(
            self.cycle_id,
            self.snapshot_id,
            (*_stage_one_records(self.stage_one), self.entry),
        )
        return self


class QuantDeveloperInput(SnapshotAgentInput):
    stage_one: StageOneContext
    entry: EntryAnalysisOutput
    quant_research: QuantResearchOutput | None = None
    performance_history: PerformanceHistoryReference | None = None

    @model_validator(mode="after")
    def validate_upstream_trace(self) -> Self:
        _validate_output_trace(
            self.cycle_id,
            self.snapshot_id,
            (*_stage_one_records(self.stage_one), self.entry, self.quant_research),
        )
        return self


class SkepticInput(SnapshotAgentInput):
    stage_one: StageOneContext
    entry: EntryAnalysisOutput
    quant_research: QuantResearchOutput | None = None
    quant_developer: QuantDeveloperOutput | None = None
    chief_draft: ChiefTraderOutput | None = None

    @model_validator(mode="after")
    def validate_upstream_trace(self) -> Self:
        _validate_output_trace(
            self.cycle_id,
            self.snapshot_id,
            (
                *_stage_one_records(self.stage_one),
                self.entry,
                self.quant_research,
                self.quant_developer,
                self.chief_draft,
            ),
        )
        return self


class ChiefTraderInput(SnapshotAgentInput):
    stage_one: StageOneContext
    entry: EntryAnalysisOutput
    quant_research: QuantResearchOutput | None = None
    quant_developer: QuantDeveloperOutput | None = None
    skeptic: SkepticOutput

    @model_validator(mode="after")
    def validate_upstream_trace(self) -> Self:
        _validate_output_trace(
            self.cycle_id,
            self.snapshot_id,
            (
                *_stage_one_records(self.stage_one),
                self.entry,
                self.quant_research,
                self.quant_developer,
                self.skeptic,
            ),
        )
        return self


class AgentOutputReference(CoreModel):
    """Stable reference to one historical output for offline review."""

    output_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    agent_role: AgentRole
    agent_version: SchemaVersion
    prompt_version: SchemaVersion


class PerformanceReviewInput(CoreModel):
    """Offline-only retrospective input, intentionally outside the live graph."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    performance_history: PerformanceHistoryReference
    agent_output_refs: tuple[AgentOutputReference, ...]
    trade_proposals: tuple[TradeProposal, ...] = ()
    risk_decisions: tuple[RiskDecision, ...] = ()


class StageMember(CoreModel):
    """One immutable component declaration inside a pipeline stage."""

    component: PipelineComponent
    required: bool
    allowed_profiles: tuple[AgentExecutionProfile, ...] = ()

    @model_validator(mode="after")
    def validate_component_profile(self) -> Self:
        if self.component is PipelineComponent.RISK_ENGINE and self.allowed_profiles:
            raise ValueError("deterministic Risk Engine must not have an agent profile")
        if self.component is not PipelineComponent.RISK_ENGINE and not self.allowed_profiles:
            raise ValueError("agent stage member requires an allowed execution profile")
        return self


class StageDefinition(CoreModel):
    """Static orchestration metadata; it performs no scheduling."""

    pipeline: PipelineKind
    stage_number: PositiveInt
    name: Identifier
    members: tuple[StageMember, ...] = Field(min_length=1)
    parallel: bool = False
    minimum_successes: NonNegativeInt

    @model_validator(mode="after")
    def validate_stage(self) -> Self:
        if len({item.component for item in self.members}) != len(self.members):
            raise ValueError("stage components must be unique")
        if self.minimum_successes > len(self.members):
            raise ValueError("minimum_successes cannot exceed stage member count")
        return self


class DebateChallenge(CoreModel):
    """One structured Skeptic challenge; unrestricted chat is not represented."""

    schema_version: SchemaVersion = "1.0.0"
    challenge_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    round_number: PositiveInt = Field(le=3)
    challenger: Literal[AgentRole.SKEPTIC] = AgentRole.SKEPTIC
    target: Literal[AgentRole.ENTRY_ANALYST, AgentRole.CHIEF_TRADER]
    challenged_output_id: Identifier
    objections: tuple[AgentEvidence, ...] = Field(min_length=1)
    produced_at: datetime

    _normalize_time = field_validator("produced_at")(_utc)
