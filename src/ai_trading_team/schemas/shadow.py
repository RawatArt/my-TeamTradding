"""Immutable M6 shadow-cycle and audit boundary contracts."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.agents import (
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
from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    CycleId,
    FiniteDecimal,
    Identifier,
    PositiveDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    ApplicationMode,
    CycleClaimState,
    PipelineComponent,
    RiskDecisionStatus,
    ShadowDisposition,
    ShadowExecutionStatus,
    ShadowOutcomeSource,
    StageExecutionStatus,
    Timeframe,
    TradeAction,
)
from ai_trading_team.schemas.orchestration import AgentFailureRecord
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision
from ai_trading_team.schemas.runtime import InvocationTelemetry, InvocationTrace

type CycleAgentOutput = (
    MarketContextOutput
    | TrendAnalysisOutput
    | PriceActionOutput
    | EntryAnalysisOutput
    | QuantResearchOutput
    | QuantDeveloperOutput
    | SkepticOutput
    | ChiefTraderOutput
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class CycleClaim(CoreModel):
    """Durable ownership marker that prevents implicit cycle replay."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    state: CycleClaimState
    claimed_at: datetime
    updated_at: datetime
    sanitized_reason: str | None = Field(default=None, max_length=512)

    _normalize_time = field_validator("claimed_at", "updated_at")(_utc)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.updated_at < self.claimed_at:
            raise ValueError("claim update must not predate the claim")
        if self.state is CycleClaimState.ABANDONED and not self.sanitized_reason:
            raise ValueError("abandoned claim requires a sanitized reason")
        if self.state is not CycleClaimState.ABANDONED and self.sanitized_reason is not None:
            raise ValueError("only an abandoned claim may carry a reason")
        return self


class StageExecutionRecord(CoreModel):
    """Ordered, trusted result for one deterministic stage execution."""

    schema_version: SchemaVersion = "1.0.0"
    stage_number: PositiveInt = Field(le=6)
    stage_name: Identifier
    components: tuple[PipelineComponent, ...] = Field(min_length=1)
    status: StageExecutionStatus
    started_at: datetime
    completed_at: datetime
    invocation_ids: tuple[Identifier, ...] = ()
    failure_ids: tuple[Identifier, ...] = ()
    sanitized_detail: str | None = Field(default=None, max_length=512)

    _normalize_time = field_validator("started_at", "completed_at")(_utc)

    @model_validator(mode="after")
    def validate_stage(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("stage completion must not predate stage start")
        if len(set(self.invocation_ids)) != len(self.invocation_ids):
            raise ValueError("stage invocation identifiers must be unique")
        if len(set(self.failure_ids)) != len(self.failure_ids):
            raise ValueError("stage failure identifiers must be unique")
        return self


class AgentInvocationAudit(CoreModel):
    """Sanitized invocation metadata without prompt bodies or raw provider responses."""

    schema_version: SchemaVersion = "1.0.0"
    stage_number: PositiveInt = Field(le=5)
    debate_round: PositiveInt | None = Field(default=None, le=3)
    trace: InvocationTrace
    telemetry: InvocationTelemetry
    output_id: Identifier | None = None
    failure_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_result_reference(self) -> Self:
        if (self.output_id is None) == (self.failure_id is None):
            raise ValueError("invocation audit requires exactly one result reference")
        if self.output_id is not None and self.output_id != self.trace.output_id:
            raise ValueError("invocation output reference must match trace")
        return self


class RiskInputAudit(CoreModel):
    """Minimized safe facts needed to audit an M3 invocation."""

    schema_version: SchemaVersion = "1.0.0"
    snapshot_digest: ContentDigest
    account_context: AccountRiskContext


class DecisionCycle(CoreModel):
    """Complete immutable result of one explicitly invoked M6 shadow cycle."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    initial_snapshot_id: SnapshotId
    symbol: Symbol
    primary_timeframe: Timeframe
    cycle_started_at: datetime
    cycle_completed_at: datetime
    app_mode: Literal[ApplicationMode.SHADOW] = ApplicationMode.SHADOW
    market_view: AgentMarketView
    risk_input_audit: RiskInputAudit
    stages: tuple[StageExecutionRecord, ...]
    invocations: tuple[AgentInvocationAudit, ...] = ()
    agent_outputs: tuple[CycleAgentOutput, ...] = ()
    agent_failures: tuple[AgentFailureRecord, ...] = ()
    chief_decisions: tuple[ChiefTraderOutput, ...] = ()
    chief_decision: ChiefTraderOutput | None = None
    trade_proposal: TradeProposal | None = None
    risk_decision: RiskDecision | None = None
    final_disposition: ShadowDisposition
    outcome_source: ShadowOutcomeSource

    _normalize_time = field_validator("cycle_started_at", "cycle_completed_at")(_utc)

    @model_validator(mode="after")
    def validate_cycle(self) -> Self:
        if self.cycle_completed_at < self.cycle_started_at:
            raise ValueError("cycle completion must not predate cycle start")
        if (
            self.market_view.cycle_id != self.cycle_id
            or self.market_view.snapshot_id != self.initial_snapshot_id
            or self.market_view.symbol != self.symbol
            or self.market_view.primary_timeframe is not self.primary_timeframe
        ):
            raise ValueError("market view must match the cycle trace")
        context = self.risk_input_audit.account_context
        if (
            context.cycle_id != self.cycle_id
            or context.snapshot_id != self.initial_snapshot_id
        ) and self.final_disposition is not ShadowDisposition.ABORTED:
            raise ValueError("account context must match the cycle trace")
        if tuple(stage.stage_number for stage in self.stages) != tuple(range(1, 7)):
            raise ValueError("cycle must retain exactly the six ordered realtime stages")
        invocation_ids = tuple(item.trace.invocation_id for item in self.invocations)
        if len(invocation_ids) != len(set(invocation_ids)):
            raise ValueError("logical invocation identifiers must be unique")
        output_ids = tuple(item.output_id for item in self.agent_outputs)
        failure_ids = tuple(item.failure_id for item in self.agent_failures)
        if len(output_ids) != len(set(output_ids)) or len(failure_ids) != len(set(failure_ids)):
            raise ValueError("agent result identifiers must be unique")
        if any(
            item.cycle_id != self.cycle_id or item.snapshot_id != self.initial_snapshot_id
            for item in (*self.agent_outputs, *self.agent_failures)
        ):
            raise ValueError("all agent results must match the cycle trace")
        referenced_outputs = {item.output_id for item in self.invocations if item.output_id}
        referenced_failures = {item.failure_id for item in self.invocations if item.failure_id}
        if referenced_outputs != set(output_ids) or not referenced_failures.issubset(
            set(failure_ids)
        ):
            raise ValueError("invocation audit references must match retained agent results")
        if self.chief_decisions and self.chief_decision != self.chief_decisions[-1]:
            raise ValueError("final Chief decision must be the last retained Chief output")
        if not self.chief_decisions and self.chief_decision is not None:
            raise ValueError("final Chief decision requires a retained Chief output")
        retained_chief = tuple(
            item for item in self.agent_outputs if isinstance(item, ChiefTraderOutput)
        )
        if retained_chief != self.chief_decisions:
            raise ValueError("Chief decision history must match retained agent outputs")
        expected_proposal = (
            self.chief_decision.payload.trade_proposal if self.chief_decision else None
        )
        if self.trade_proposal != expected_proposal:
            raise ValueError("trade proposal must match the final Chief decision")
        if self.risk_decision is not None:
            if self.trade_proposal is None:
                raise ValueError("Risk decision requires a trade proposal")
            if (
                self.risk_decision.cycle_id != self.cycle_id
                or self.risk_decision.snapshot_id != self.initial_snapshot_id
                or self.risk_decision.proposal_id != self.trade_proposal.proposal_id
            ):
                raise ValueError("Risk decision must match the cycle and proposal")
        if self.final_disposition is ShadowDisposition.CHIEF_HOLD:
            if (
                self.chief_decision is None
                or self.chief_decision.payload.action is not TradeAction.HOLD
            ):
                raise ValueError("CHIEF_HOLD requires a valid Chief HOLD output")
            if self.risk_decision is not None:
                raise ValueError("Chief HOLD must skip deterministic Risk")
        if self.final_disposition in {
            ShadowDisposition.WOULD_BUY,
            ShadowDisposition.WOULD_SELL,
        }:
            expected_action = (
                TradeAction.BUY
                if self.final_disposition is ShadowDisposition.WOULD_BUY
                else TradeAction.SELL
            )
            if (
                self.chief_decision is None
                or self.chief_decision.payload.action is not expected_action
                or self.risk_decision is None
                or self.risk_decision.status is not RiskDecisionStatus.APPROVED
            ):
                raise ValueError("WOULD_BUY/WOULD_SELL requires matching approved Risk")
        if self.final_disposition is ShadowDisposition.RISK_REJECTED and (
            self.risk_decision is None
            or self.risk_decision.status is not RiskDecisionStatus.REJECTED
        ):
            raise ValueError("RISK_REJECTED requires a rejected Risk decision")
        if self.final_disposition is ShadowDisposition.RISK_HALTED and (
            self.risk_decision is None
            or self.risk_decision.status is not RiskDecisionStatus.HALTED
        ):
            raise ValueError("RISK_HALTED requires a halted Risk decision")
        return self


class ShadowTradeIntent(CoreModel):
    """Non-executable record of what an approved proposal would have requested."""

    schema_version: SchemaVersion = "1.0.0"
    cycle_id: CycleId
    snapshot_id: SnapshotId
    proposal: TradeProposal
    risk_decision: RiskDecision
    selected_volume: PositiveDecimal
    hypothetical_entry: FiniteDecimal
    hypothetical_stop_loss: FiniteDecimal
    hypothetical_take_profit: FiniteDecimal
    recorded_at: datetime
    execution_status: Literal[ShadowExecutionStatus.NOT_EXECUTED_SHADOW] = (
        ShadowExecutionStatus.NOT_EXECUTED_SHADOW
    )

    _normalize_time = field_validator("recorded_at")(_utc)

    @model_validator(mode="after")
    def validate_approved_intent(self) -> Self:
        sizing = self.risk_decision.position_sizing
        if self.risk_decision.status is not RiskDecisionStatus.APPROVED or sizing is None:
            raise ValueError("shadow intent requires an approved Risk decision")
        if sizing.selected_volume != self.selected_volume:
            raise ValueError("shadow volume must exactly match approved sizing")
        if (
            self.proposal.entry is None
            or self.proposal.stop_loss is None
            or self.proposal.take_profit is None
        ):
            raise ValueError("approved shadow intent requires entry, stop, and target")
        if (
            self.hypothetical_entry != self.proposal.entry
            or self.hypothetical_stop_loss != self.proposal.stop_loss
            or self.hypothetical_take_profit != self.proposal.take_profit
        ):
            raise ValueError("shadow prices must exactly match the proposal")
        if (
            self.cycle_id != self.proposal.cycle_id
            or self.snapshot_id != self.proposal.snapshot_id
            or self.cycle_id != self.risk_decision.cycle_id
            or self.snapshot_id != self.risk_decision.snapshot_id
        ):
            raise ValueError("shadow intent trace must match proposal and Risk decision")
        return self


class ShadowDecisionRecord(CoreModel):
    """Persisted final M6 record; it cannot express an executable action."""

    schema_version: SchemaVersion = "1.0.0"
    record_id: Identifier
    recorded_at: datetime
    decision_cycle: DecisionCycle
    shadow_trade_intent: ShadowTradeIntent | None = None

    _normalize_time = field_validator("recorded_at")(_utc)

    @model_validator(mode="after")
    def validate_record(self) -> Self:
        cycle = self.decision_cycle
        approved = cycle.risk_decision is not None and (
            cycle.risk_decision.status is RiskDecisionStatus.APPROVED
        )
        if approved != (self.shadow_trade_intent is not None):
            raise ValueError("only an approved Risk decision creates a shadow trade intent")
        if self.shadow_trade_intent is not None and (
            self.shadow_trade_intent.cycle_id != cycle.cycle_id
            or self.shadow_trade_intent.snapshot_id != cycle.initial_snapshot_id
        ):
            raise ValueError("shadow intent must match its decision cycle")
        return self
