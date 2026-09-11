"""One-shot M6 multi-agent SHADOW decision-cycle runtime."""

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from pydantic import Field

from ai_trading_team.orchestration.context import AgentInputFactory
from ai_trading_team.orchestration.identifiers import (
    logical_invocation_id,
    shadow_record_id,
)
from ai_trading_team.orchestration.preflight import (
    ShadowPreflightError,
    validate_shadow_inputs,
)
from ai_trading_team.orchestration.protocols import DeterministicRiskStage
from ai_trading_team.orchestration.runtime import ShadowAgentInvoker
from ai_trading_team.runtime.contracts import contract_for_role
from ai_trading_team.runtime.errors import RuntimeInvocationError
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
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    AgentRole,
    FailureDisposition,
    FreshnessState,
    PipelineComponent,
    QuantStageSelection,
    RiskDecisionStatus,
    RuntimeFailureCategory,
    ShadowDisposition,
    ShadowOutcomeSource,
    StageExecutionStatus,
    TradeAction,
)
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.orchestration import AgentFailureRecord, StageOneContext
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision
from ai_trading_team.schemas.shadow import (
    AgentInvocationAudit,
    CycleAgentOutput,
    DecisionCycle,
    RiskInputAudit,
    ShadowDecisionRecord,
    ShadowTradeIntent,
    StageExecutionRecord,
)
from ai_trading_team.storage.shadow_audit import ShadowAuditRepository


class ShadowCyclePolicy(CoreModel):
    """Immutable orchestration choices fixed before a cycle begins."""

    debate_rounds: int = Field(default=1, ge=1, le=3)
    quant_stage_selection: QuantStageSelection = QuantStageSelection.SKIP


@dataclass(frozen=True, slots=True)
class _InvocationOutcome:
    output: CoreModel | None
    failure: AgentFailureRecord | None
    audit: AgentInvocationAudit | None
    invocation_id: str


_STAGE_COMPONENTS = {
    1: (
        PipelineComponent.MARKET_CONTEXT,
        PipelineComponent.TREND_ANALYST,
        PipelineComponent.PRICE_ACTION_ANALYST,
    ),
    2: (PipelineComponent.ENTRY_ANALYST,),
    3: (
        PipelineComponent.QUANT_RESEARCHER,
        PipelineComponent.SENIOR_QUANT_DEVELOPER,
    ),
    4: (PipelineComponent.SKEPTIC,),
    5: (PipelineComponent.CHIEF_TRADER,),
    6: (PipelineComponent.RISK_ENGINE,),
}

_STAGE_NAMES = {
    1: "parallel-analysis",
    2: "entry-analysis",
    3: "conditional-quant-review",
    4: "skeptic-review",
    5: "chief-decision",
    6: "deterministic-risk",
}

_ROLE_COMPONENT = {
    AgentRole.MARKET_CONTEXT: PipelineComponent.MARKET_CONTEXT,
    AgentRole.TREND_ANALYST: PipelineComponent.TREND_ANALYST,
    AgentRole.PRICE_ACTION_ANALYST: PipelineComponent.PRICE_ACTION_ANALYST,
    AgentRole.ENTRY_ANALYST: PipelineComponent.ENTRY_ANALYST,
    AgentRole.QUANT_RESEARCHER: PipelineComponent.QUANT_RESEARCHER,
    AgentRole.SENIOR_QUANT_DEVELOPER: PipelineComponent.SENIOR_QUANT_DEVELOPER,
    AgentRole.SKEPTIC: PipelineComponent.SKEPTIC,
    AgentRole.CHIEF_TRADER: PipelineComponent.CHIEF_TRADER,
}


class ShadowCycleOrchestrator:
    """Execute one accepted M4 graph and persist a non-executable shadow result."""

    def __init__(
        self,
        *,
        invoker: ShadowAgentInvoker,
        risk_engine: DeterministicRiskStage,
        repository: ShadowAuditRepository,
        policy: ShadowCyclePolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._invoker = invoker
        self._risk = risk_engine
        self._repository = repository
        self._policy = policy or ShadowCyclePolicy()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run_shadow_cycle(
        self,
        snapshot: MarketSnapshot,
        account_risk_context: AccountRiskContext,
    ) -> ShadowDecisionRecord:
        """Run exactly one claimed SHADOW cycle; never schedule or execute a trade."""
        started_at = self._now()
        self._repository.claim_cycle(
            snapshot.cycle_id,
            snapshot.snapshot_id,
            at=started_at,
        )
        market = AgentMarketView.from_snapshot(snapshot)
        state = _CycleState(snapshot, account_risk_context, market, started_at)
        try:
            validate_shadow_inputs(snapshot, account_risk_context, started_at)
        except ShadowPreflightError as exc:
            state.add_system_failure(
                AgentFailureCategory.SCHEMA_MISMATCH,
                "shadow input compatibility preflight failed",
                self._now(),
            )
            state.set_stage(1, StageExecutionStatus.ABORTED, self._now(), str(exc))
            return self._finish(
                state,
                ShadowDisposition.ABORTED,
                ShadowOutcomeSource.ORCHESTRATOR,
            )

        if market.freshness.overall is FreshnessState.STALE:
            state.add_system_failure(
                AgentFailureCategory.STALE_SNAPSHOT,
                "valid snapshot is stale under SHADOW decision policy",
                self._now(),
            )
            state.set_stage(1, StageExecutionStatus.HOLD, self._now(), "stale snapshot")
            return self._finish(
                state,
                ShadowDisposition.POLICY_HOLD,
                ShadowOutcomeSource.FAILURE_POLICY,
            )

        factory = AgentInputFactory(market)
        stage_one_started = self._now()
        stage_one_calls = (
            self._invoke(AgentRole.MARKET_CONTEXT, factory.market_context(), 1),
            self._invoke(AgentRole.TREND_ANALYST, factory.trend(), 1),
            self._invoke(AgentRole.PRICE_ACTION_ANALYST, factory.price_action(), 1),
        )
        stage_one_outcomes = await asyncio.gather(*stage_one_calls)
        for outcome in stage_one_outcomes:
            state.retain(outcome)
        successes = sum(item.output is not None for item in stage_one_outcomes)
        terminal = self._stage_one_terminal(stage_one_outcomes, successes, state)
        if terminal is not None:
            status, disposition = terminal
            state.set_stage(1, status, stage_one_started)
            return self._finish(state, disposition, ShadowOutcomeSource.FAILURE_POLICY)
        stage_one_failures = tuple(
            self._with_disposition(item.failure, FailureDisposition.CONTINUE_DEGRADED)
            for item in stage_one_outcomes
            if item.failure is not None
        )
        state.replace_failures(stage_one_failures)
        stage_one = StageOneContext(
            market_context=self._typed_output(stage_one_outcomes[0], MarketContextOutput),
            trend=self._typed_output(stage_one_outcomes[1], TrendAnalysisOutput),
            price_action=self._typed_output(stage_one_outcomes[2], PriceActionOutput),
            failures=stage_one_failures,
        )
        state.set_stage(
            1,
            StageExecutionStatus.DEGRADED if stage_one_failures else StageExecutionStatus.COMPLETED,
            stage_one_started,
        )

        stage_two_started = self._now()
        entry_outcome = await self._invoke(AgentRole.ENTRY_ANALYST, factory.entry(stage_one), 2)
        state.retain(entry_outcome)
        if entry_outcome.failure is not None:
            return self._failure_finish(state, 2, stage_two_started, entry_outcome.failure)
        entry = self._typed_output(entry_outcome, EntryAnalysisOutput)
        assert entry is not None
        state.set_stage(2, StageExecutionStatus.COMPLETED, stage_two_started)

        quant, quant_developer, quant_terminal = await self._run_quant_stage(
            state, factory, stage_one, entry
        )
        if quant_terminal is not None:
            return quant_terminal

        chief_draft: ChiefTraderOutput | None = None
        final_skeptic: SkepticOutput | None = None
        debate_started = self._now()
        for round_number in range(1, self._policy.debate_rounds + 1):
            skeptic_outcome = await self._invoke(
                AgentRole.SKEPTIC,
                factory.skeptic(stage_one, entry, quant, quant_developer, chief_draft),
                4,
                round_number,
            )
            state.retain(skeptic_outcome)
            if skeptic_outcome.failure is not None:
                state.set_stage(4, StageExecutionStatus.HOLD, debate_started)
                return self._failure_finish(
                    state, 5, debate_started, skeptic_outcome.failure, stage_already_recorded=True
                )
            final_skeptic = self._typed_output(skeptic_outcome, SkepticOutput)
            assert final_skeptic is not None

            chief_outcome = await self._invoke(
                AgentRole.CHIEF_TRADER,
                factory.chief(stage_one, entry, quant, quant_developer, final_skeptic),
                5,
                round_number,
            )
            state.retain(chief_outcome)
            if chief_outcome.failure is not None:
                state.set_stage(4, StageExecutionStatus.COMPLETED, debate_started)
                return self._failure_finish(
                    state, 5, debate_started, chief_outcome.failure, stage_already_recorded=True
                )
            chief_draft = self._typed_output(chief_outcome, ChiefTraderOutput)
            assert chief_draft is not None
            state.chief_decisions.append(chief_draft)
            if chief_draft.payload.action is TradeAction.HOLD:
                break

        state.set_stage(4, StageExecutionStatus.COMPLETED, debate_started)
        state.set_stage(5, StageExecutionStatus.COMPLETED, debate_started)
        assert chief_draft is not None
        state.chief_decision = chief_draft
        proposal = chief_draft.payload.trade_proposal
        state.trade_proposal = proposal
        if chief_draft.payload.action is TradeAction.HOLD:
            state.set_stage(6, StageExecutionStatus.SKIPPED, self._now(), "Chief HOLD")
            return self._finish(
                state,
                ShadowDisposition.CHIEF_HOLD,
                ShadowOutcomeSource.CHIEF_TRADER,
            )

        assert proposal is not None
        risk_started = self._now()
        try:
            risk_decision = self._risk.evaluate(
                proposal,
                snapshot,
                account_risk_context,
                self._now(),
            )
        except Exception:
            state.add_system_failure(
                AgentFailureCategory.UNKNOWN,
                "deterministic Risk stage raised an unexpected error",
                self._now(),
            )
            state.set_stage(6, StageExecutionStatus.ABORTED, risk_started)
            return self._finish(
                state,
                ShadowDisposition.ABORTED,
                ShadowOutcomeSource.ORCHESTRATOR,
            )
        state.risk_decision = risk_decision
        state.set_stage(6, StageExecutionStatus.COMPLETED, risk_started)
        if risk_decision.status is RiskDecisionStatus.HALTED:
            return self._finish(
                state,
                ShadowDisposition.RISK_HALTED,
                ShadowOutcomeSource.RISK_ENGINE,
            )
        if risk_decision.status is RiskDecisionStatus.REJECTED:
            return self._finish(
                state,
                ShadowDisposition.RISK_REJECTED,
                ShadowOutcomeSource.RISK_ENGINE,
            )
        disposition = (
            ShadowDisposition.WOULD_BUY
            if chief_draft.payload.action is TradeAction.BUY
            else ShadowDisposition.WOULD_SELL
        )
        return self._finish(state, disposition, ShadowOutcomeSource.RISK_ENGINE)

    async def _run_quant_stage(
        self,
        state: "_CycleState",
        factory: AgentInputFactory,
        stage_one: StageOneContext,
        entry: EntryAnalysisOutput,
    ) -> tuple[
        QuantResearchOutput | None,
        QuantDeveloperOutput | None,
        ShadowDecisionRecord | None,
    ]:
        started = self._now()
        selection = self._policy.quant_stage_selection
        if selection is QuantStageSelection.SKIP:
            state.set_stage(3, StageExecutionStatus.SKIPPED, started, "quant stage not selected")
            return None, None, None
        quant_outcome = await self._invoke(
            AgentRole.QUANT_RESEARCHER,
            factory.quant_research(stage_one, entry),
            3,
        )
        state.retain(quant_outcome)
        if quant_outcome.failure is not None:
            disposition = self._failure_disposition(quant_outcome.failure)
            if disposition is not FailureDisposition.CONTINUE_DEGRADED:
                return None, None, self._failure_finish(
                    state, 3, started, quant_outcome.failure
                )
        quant = self._typed_output(quant_outcome, QuantResearchOutput)
        developer: QuantDeveloperOutput | None = None
        if selection is QuantStageSelection.QUANT_AND_SENIOR_REVIEW:
            developer_outcome = await self._invoke(
                AgentRole.SENIOR_QUANT_DEVELOPER,
                factory.quant_developer(stage_one, entry, quant),
                3,
            )
            state.retain(developer_outcome)
            if developer_outcome.failure is not None:
                disposition = self._failure_disposition(developer_outcome.failure)
                if disposition is not FailureDisposition.CONTINUE_DEGRADED:
                    return quant, None, self._failure_finish(
                        state, 3, started, developer_outcome.failure
                    )
            developer = self._typed_output(developer_outcome, QuantDeveloperOutput)
        degraded = any(
            failure.agent_role
            in {AgentRole.QUANT_RESEARCHER, AgentRole.SENIOR_QUANT_DEVELOPER}
            for failure in state.failures
        )
        state.set_stage(
            3,
            StageExecutionStatus.DEGRADED if degraded else StageExecutionStatus.COMPLETED,
            started,
        )
        return quant, developer, None

    async def _invoke(
        self,
        role: AgentRole,
        context: CoreModel,
        stage_number: int,
        debate_round: int | None = None,
    ) -> _InvocationOutcome:
        expected_id = logical_invocation_id(
            str(context.model_dump()["cycle_id"]),
            str(context.model_dump()["snapshot_id"]),
            stage_number,
            role,
            debate_round,
        )
        try:
            result = await self._invoker.invoke(
                role,
                context,
                stage_number=stage_number,
                debate_round=debate_round,
            )
        except RuntimeInvocationError as exc:
            failure = self._runtime_failure(role, context, expected_id, exc.category, exc.detail)
            return _InvocationOutcome(None, failure, None, expected_id)
        except (KeyError, TypeError, ValueError):
            failure = self._runtime_failure(
                role,
                context,
                expected_id,
                RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                "configured agent runtime is unavailable or incompatible",
            )
            return _InvocationOutcome(None, failure, None, expected_id)
        except Exception:
            failure = self._runtime_failure(
                role,
                context,
                expected_id,
                RuntimeFailureCategory.UNKNOWN_PROVIDER_ERROR,
                "agent invocation failed unexpectedly",
            )
            return _InvocationOutcome(None, failure, None, expected_id)

        if result.trace.invocation_id != expected_id or result.trace.agent_role is not role:
            failure = self._runtime_failure(
                role,
                context,
                expected_id,
                RuntimeFailureCategory.SCHEMA_INCOMPATIBLE,
                "agent invocation trace is incompatible with the cycle structure",
            )
            audit = AgentInvocationAudit(
                stage_number=stage_number,
                debate_round=debate_round,
                trace=result.trace,
                telemetry=result.telemetry,
                failure_id=failure.failure_id,
            )
            return _InvocationOutcome(None, failure, audit, expected_id)
        if result.output is not None:
            contract = contract_for_role(role)
            if not isinstance(result.output, contract.output_type):
                failure = self._runtime_failure(
                    role,
                    context,
                    expected_id,
                    RuntimeFailureCategory.INVALID_MODEL_OUTPUT,
                    "runtime output does not match the role contract",
                )
                audit = AgentInvocationAudit(
                    stage_number=stage_number,
                    debate_round=debate_round,
                    trace=result.trace,
                    telemetry=result.telemetry,
                    failure_id=failure.failure_id,
                )
                return _InvocationOutcome(None, failure, audit, expected_id)
            audit = AgentInvocationAudit(
                stage_number=stage_number,
                debate_round=debate_round,
                trace=result.trace,
                telemetry=result.telemetry,
                output_id=cast(CycleAgentOutput, result.output).output_id,
            )
            return _InvocationOutcome(result.output, None, audit, expected_id)
        assert result.failure is not None and result.runtime_failure_category is not None
        category = self._runtime_category(result.runtime_failure_category)
        failure = AgentFailureRecord.model_validate(
            {
                **result.failure.model_dump(mode="python"),
                "category": category,
                "disposition": self._category_disposition(category, role),
            }
        )
        audit = AgentInvocationAudit(
            stage_number=stage_number,
            debate_round=debate_round,
            trace=result.trace,
            telemetry=result.telemetry,
            failure_id=failure.failure_id,
        )
        return _InvocationOutcome(None, failure, audit, expected_id)

    def _stage_one_terminal(
        self,
        outcomes: tuple[_InvocationOutcome, ...] | list[_InvocationOutcome],
        successes: int,
        state: "_CycleState",
    ) -> tuple[StageExecutionStatus, ShadowDisposition] | None:
        failures = tuple(item.failure for item in outcomes if item.failure is not None)
        if any(
            self._failure_disposition(item) is FailureDisposition.ABORT_CYCLE
            for item in failures
        ):
            return StageExecutionStatus.ABORTED, ShadowDisposition.ABORTED
        if any(item.category is AgentFailureCategory.INVALID_OUTPUT for item in failures):
            return StageExecutionStatus.HOLD, ShadowDisposition.POLICY_HOLD
        if successes < 2:
            return StageExecutionStatus.HOLD, ShadowDisposition.POLICY_HOLD
        return None

    def _failure_finish(
        self,
        state: "_CycleState",
        stage_number: int,
        started_at: datetime,
        failure: AgentFailureRecord,
        *,
        stage_already_recorded: bool = False,
    ) -> ShadowDecisionRecord:
        disposition = self._failure_disposition(failure)
        if not stage_already_recorded:
            state.set_stage(
                stage_number,
                StageExecutionStatus.ABORTED
                if disposition is FailureDisposition.ABORT_CYCLE
                else StageExecutionStatus.HOLD,
                started_at,
            )
        return self._finish(
            state,
            ShadowDisposition.ABORTED
            if disposition is FailureDisposition.ABORT_CYCLE
            else ShadowDisposition.POLICY_HOLD,
            ShadowOutcomeSource.FAILURE_POLICY,
        )

    def _finish(
        self,
        state: "_CycleState",
        disposition: ShadowDisposition,
        source: ShadowOutcomeSource,
    ) -> ShadowDecisionRecord:
        completed_at = self._now()
        state.fill_skipped(completed_at)
        cycle = DecisionCycle(
            cycle_id=state.snapshot.cycle_id,
            initial_snapshot_id=state.snapshot.snapshot_id,
            symbol=state.snapshot.symbol,
            primary_timeframe=state.snapshot.primary_timeframe,
            cycle_started_at=state.started_at,
            cycle_completed_at=completed_at,
            market_view=state.market,
            risk_input_audit=RiskInputAudit(
                snapshot_digest=_digest(state.snapshot),
                account_context=state.account_context,
            ),
            stages=tuple(state.stages[index] for index in range(1, 7)),
            invocations=tuple(state.invocations),
            agent_outputs=tuple(state.outputs),
            agent_failures=tuple(state.failures),
            chief_decisions=tuple(state.chief_decisions),
            chief_decision=state.chief_decision,
            trade_proposal=state.trade_proposal,
            risk_decision=state.risk_decision,
            final_disposition=disposition,
            outcome_source=source,
        )
        intent = self._shadow_intent(cycle, completed_at)
        record = ShadowDecisionRecord(
            record_id=shadow_record_id(cycle.cycle_id, cycle.initial_snapshot_id),
            recorded_at=completed_at,
            decision_cycle=cycle,
            shadow_trade_intent=intent,
        )
        self._repository.finalize(record)
        return record

    @staticmethod
    def _shadow_intent(cycle: DecisionCycle, at: datetime) -> ShadowTradeIntent | None:
        risk = cycle.risk_decision
        proposal = cycle.trade_proposal
        if risk is None or risk.status is not RiskDecisionStatus.APPROVED:
            return None
        assert proposal is not None and risk.position_sizing is not None
        assert risk.position_sizing.selected_volume is not None
        assert proposal.entry is not None
        assert proposal.stop_loss is not None
        assert proposal.take_profit is not None
        return ShadowTradeIntent(
            cycle_id=cycle.cycle_id,
            snapshot_id=cycle.initial_snapshot_id,
            proposal=proposal,
            risk_decision=risk,
            selected_volume=risk.position_sizing.selected_volume,
            hypothetical_entry=proposal.entry,
            hypothetical_stop_loss=proposal.stop_loss,
            hypothetical_take_profit=proposal.take_profit,
            recorded_at=at,
        )

    def _runtime_failure(
        self,
        role: AgentRole,
        context: CoreModel,
        invocation_id: str,
        runtime_category: RuntimeFailureCategory,
        detail: str,
    ) -> AgentFailureRecord:
        category = self._runtime_category(runtime_category)
        digest = hashlib.sha256(invocation_id.encode()).hexdigest()[:16]
        return AgentFailureRecord(
            failure_id=f"failure-{digest}",
            cycle_id=str(context.model_dump()["cycle_id"]),
            snapshot_id=str(context.model_dump()["snapshot_id"]),
            agent_role=role,
            category=category,
            occurred_at=self._now(),
            sanitized_detail=detail,
            disposition=self._category_disposition(category, role),
        )

    @staticmethod
    def _runtime_category(category: RuntimeFailureCategory) -> AgentFailureCategory:
        if category is RuntimeFailureCategory.PROVIDER_TIMEOUT:
            return AgentFailureCategory.TIMEOUT
        if category is RuntimeFailureCategory.INVALID_MODEL_OUTPUT:
            return AgentFailureCategory.INVALID_OUTPUT
        if category in {
            RuntimeFailureCategory.SCHEMA_INCOMPATIBLE,
            RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE,
            RuntimeFailureCategory.DUPLICATE_INVOCATION,
            RuntimeFailureCategory.INVALID_REQUEST,
            RuntimeFailureCategory.INVALID_PROMPT_REFERENCE,
        }:
            return AgentFailureCategory.SCHEMA_MISMATCH
        if category in {
            RuntimeFailureCategory.BUDGET_EXCEEDED,
            RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
            RuntimeFailureCategory.PROVIDER_AUTHENTICATION,
            RuntimeFailureCategory.PROVIDER_PERMISSION,
            RuntimeFailureCategory.PROVIDER_RATE_LIMIT,
            RuntimeFailureCategory.PROVIDER_TRANSIENT,
            RuntimeFailureCategory.PROVIDER_REFUSAL,
        }:
            return AgentFailureCategory.UNAVAILABLE_AGENT
        return AgentFailureCategory.UNKNOWN

    @staticmethod
    def _category_disposition(
        category: AgentFailureCategory, role: AgentRole
    ) -> FailureDisposition:
        if category in {
            AgentFailureCategory.SCHEMA_MISMATCH,
            AgentFailureCategory.UNKNOWN,
        }:
            return FailureDisposition.ABORT_CYCLE
        if category in {AgentFailureCategory.TIMEOUT, AgentFailureCategory.UNAVAILABLE_AGENT} and (
            role in {AgentRole.QUANT_RESEARCHER, AgentRole.SENIOR_QUANT_DEVELOPER}
        ):
            return FailureDisposition.CONTINUE_DEGRADED
        return FailureDisposition.HOLD

    @staticmethod
    def _failure_disposition(failure: AgentFailureRecord) -> FailureDisposition:
        return failure.disposition

    @staticmethod
    def _with_disposition(
        failure: AgentFailureRecord | None,
        disposition: FailureDisposition,
    ) -> AgentFailureRecord:
        assert failure is not None
        return AgentFailureRecord.model_validate(
            {**failure.model_dump(mode="python"), "disposition": disposition}
        )

    @staticmethod
    def _typed_output[OutputT: CoreModel](
        outcome: _InvocationOutcome,
        expected: type[OutputT],
    ) -> OutputT | None:
        if outcome.output is None:
            return None
        return outcome.output if isinstance(outcome.output, expected) else None

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("orchestrator clock must return a timezone-aware timestamp")
        return value.astimezone(UTC)


class _CycleState:
    def __init__(
        self,
        snapshot: MarketSnapshot,
        account_context: AccountRiskContext,
        market: AgentMarketView,
        started_at: datetime,
    ) -> None:
        self.snapshot = snapshot
        self.account_context = account_context
        self.market = market
        self.started_at = started_at
        self.stages: dict[int, StageExecutionRecord] = {}
        self.invocations: list[AgentInvocationAudit] = []
        self.outputs: list[CycleAgentOutput] = []
        self.failures: list[AgentFailureRecord] = []
        self.chief_decisions: list[ChiefTraderOutput] = []
        self.chief_decision: ChiefTraderOutput | None = None
        self.trade_proposal: TradeProposal | None = None
        self.risk_decision: RiskDecision | None = None

    def retain(self, outcome: _InvocationOutcome) -> None:
        if outcome.audit is not None:
            self.invocations.append(outcome.audit)
        if outcome.output is not None:
            self.outputs.append(cast(CycleAgentOutput, outcome.output))
        if outcome.failure is not None:
            self.failures.append(outcome.failure)

    def replace_failures(self, replacements: tuple[AgentFailureRecord, ...]) -> None:
        by_id = {item.failure_id: item for item in replacements}
        self.failures = [by_id.get(item.failure_id, item) for item in self.failures]

    def add_system_failure(
        self, category: AgentFailureCategory, detail: str, at: datetime
    ) -> None:
        material = f"{self.snapshot.cycle_id}\0{category.value}".encode()
        self.failures.append(
            AgentFailureRecord(
                failure_id=f"failure-{hashlib.sha256(material).hexdigest()[:16]}",
                cycle_id=self.snapshot.cycle_id,
                snapshot_id=self.snapshot.snapshot_id,
                category=category,
                occurred_at=at,
                sanitized_detail=detail,
                disposition=(
                    FailureDisposition.ABORT_CYCLE
                    if category
                    in {AgentFailureCategory.SCHEMA_MISMATCH, AgentFailureCategory.UNKNOWN}
                    else FailureDisposition.HOLD
                ),
            )
        )

    def set_stage(
        self,
        number: int,
        status: StageExecutionStatus,
        started_at: datetime,
        detail: str | None = None,
    ) -> None:
        invocation_ids = tuple(
            item.trace.invocation_id
            for item in self.invocations
            if item.stage_number == number
        )
        failure_ids = tuple(
            item.failure_id
            for item in self.failures
            if item.agent_role is not None
            and _ROLE_COMPONENT[item.agent_role] in _STAGE_COMPONENTS[number]
        )
        self.stages[number] = StageExecutionRecord(
            stage_number=number,
            stage_name=_STAGE_NAMES[number],
            components=_STAGE_COMPONENTS[number],
            status=status,
            started_at=started_at,
            completed_at=started_at,
            invocation_ids=invocation_ids,
            failure_ids=failure_ids,
            sanitized_detail=detail,
        )

    def fill_skipped(self, at: datetime) -> None:
        for number in range(1, 7):
            if number not in self.stages:
                self.set_stage(number, StageExecutionStatus.SKIPPED, at, "not reached")


def _digest(model: CoreModel) -> str:
    return f"sha256:{hashlib.sha256(model.model_dump_json().encode()).hexdigest()}"
