"""Typed M4 fixtures with no model, network, terminal, or execution behavior."""

from decimal import Decimal

from ai_trading_team.schemas.agents import (
    AgentDescriptor,
    AgentMarketView,
    ChiefTraderOutput,
    ChiefTraderResult,
    EntryAnalysisOutput,
    EntryAnalysisResult,
    MarketContextOutput,
    MarketContextResult,
    PerformanceReviewOutput,
    PerformanceReviewResult,
    PriceActionOutput,
    PriceActionResult,
    PromptReference,
    QuantDeveloperOutput,
    QuantDeveloperReview,
    QuantResearchOutput,
    QuantResearchResult,
    SkepticOutput,
    SkepticReview,
    TrendAnalysisOutput,
    TrendAnalysisResult,
)
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentInvocationMode,
    AgentOutputStatus,
    AgentRole,
    DirectionalBias,
    EntryDisposition,
    MarketRegime,
    QuantEvidenceStatus,
    QuantReviewStatus,
    SkepticVerdict,
    TradeAction,
    TrendStrength,
)
from ai_trading_team.schemas.orchestration import StageOneContext
from tests.fakes.risk import CYCLE_ID, EVALUATED_AT, SNAPSHOT_ID, proposal, risk_snapshot


def market_view() -> AgentMarketView:
    return AgentMarketView.from_snapshot(risk_snapshot())


def descriptor(
    role: AgentRole,
    *,
    execution_profile: AgentExecutionProfile | None = None,
) -> AgentDescriptor:
    if execution_profile is None:
        if role is AgentRole.PERFORMANCE_REVIEWER:
            execution_profile = AgentExecutionProfile.OFFLINE
        elif role in {AgentRole.QUANT_RESEARCHER, AgentRole.SENIOR_QUANT_DEVELOPER}:
            execution_profile = AgentExecutionProfile.CONDITIONAL
        else:
            execution_profile = AgentExecutionProfile.REALTIME
    invocation_mode = {
        AgentExecutionProfile.REALTIME: AgentInvocationMode.REALTIME,
        AgentExecutionProfile.CONDITIONAL: AgentInvocationMode.CANDIDATE_ONLY,
        AgentExecutionProfile.OFFLINE: AgentInvocationMode.OFFLINE,
    }[execution_profile]
    return AgentDescriptor(
        agent_name=role.value.casefold(),
        role=role,
        agent_version="1.0.0",
        prompt_ref=PromptReference(
            prompt_id=f"{role.value.casefold()}-prompt",
            prompt_version="1.0.0",
        ),
        execution_profile=execution_profile,
        runtime_profile_ref="runtime-unassigned",
        invocation_mode=invocation_mode,
        invocation_policy_ref="invocation-default",
        cost_policy_ref="cost-policy-unassigned",
    )


def _envelope(role: AgentRole, output_id: str) -> dict[str, object]:
    configured = descriptor(role)
    return {
        "output_id": output_id,
        "cycle_id": CYCLE_ID,
        "snapshot_id": SNAPSHOT_ID,
        "agent_name": configured.agent_name,
        "agent_role": role,
        "agent_version": configured.agent_version,
        "prompt_ref": configured.prompt_ref,
        "runtime_profile_ref": configured.runtime_profile_ref,
        "invocation_policy_ref": configured.invocation_policy_ref,
        "cost_policy_ref": configured.cost_policy_ref,
        "produced_at": EVALUATED_AT,
        "status": AgentOutputStatus.SUCCESS,
        "confidence": Decimal("0.50"),
    }


def market_context_output() -> MarketContextOutput:
    return MarketContextOutput.model_validate(
        {
            **_envelope(AgentRole.MARKET_CONTEXT, "output-market-context"),
            "payload": MarketContextResult(
                regime=MarketRegime.UNCERTAIN, summary="Mixed environment"
            ),
        }
    )


def trend_output() -> TrendAnalysisOutput:
    return TrendAnalysisOutput.model_validate(
        {
            **_envelope(AgentRole.TREND_ANALYST, "output-trend"),
            "payload": TrendAnalysisResult(
                bias=DirectionalBias.NEUTRAL,
                strength=TrendStrength.UNCERTAIN,
                summary="No clear trend",
            ),
        }
    )


def price_action_output() -> PriceActionOutput:
    return PriceActionOutput.model_validate(
        {
            **_envelope(AgentRole.PRICE_ACTION_ANALYST, "output-price-action"),
            "payload": PriceActionResult(
                bias=DirectionalBias.NEUTRAL,
                facts=("Completed candles remain inside the recent range",),
                interpretations=("Breakout direction is uncertain",),
            ),
        }
    )


def entry_output() -> EntryAnalysisOutput:
    return EntryAnalysisOutput.model_validate(
        {
            **_envelope(AgentRole.ENTRY_ANALYST, "output-entry"),
            "payload": EntryAnalysisResult(
                disposition=EntryDisposition.NO_ENTRY,
                rationale="No validated entry",
            ),
        }
    )


def quant_output() -> QuantResearchOutput:
    return QuantResearchOutput.model_validate(
        {
            **_envelope(AgentRole.QUANT_RESEARCHER, "output-quant-research"),
            "payload": QuantResearchResult(
                hypothesis="A testable hypothesis would be required",
                status=QuantEvidenceStatus.INCONCLUSIVE,
                limitations=("No experiment was run in M4",),
            ),
        }
    )


def quant_developer_output() -> QuantDeveloperOutput:
    return QuantDeveloperOutput.model_validate(
        {
            **_envelope(AgentRole.SENIOR_QUANT_DEVELOPER, "output-quant-developer"),
            "payload": QuantDeveloperReview(
                status=QuantReviewStatus.CAUTION,
                required_evidence=("Out-of-sample evidence is absent",),
            ),
        }
    )


def skeptic_output() -> SkepticOutput:
    return SkepticOutput.model_validate(
        {
            **_envelope(AgentRole.SKEPTIC, "output-skeptic"),
            "payload": SkepticReview(
                verdict=SkepticVerdict.CAUTION,
                challenged_output_ids=("output-entry",),
                objections=("Entry evidence is insufficient",),
            ),
        }
    )


def chief_output(action: TradeAction = TradeAction.HOLD) -> ChiefTraderOutput:
    trade_proposal = proposal() if action is TradeAction.BUY else None
    return ChiefTraderOutput.model_validate(
        {
            **_envelope(AgentRole.CHIEF_TRADER, "output-chief"),
            "payload": ChiefTraderResult(
                action=action,
                rationale="Typed contract fixture",
                trade_proposal=trade_proposal,
            ),
        }
    )


def performance_output() -> PerformanceReviewOutput:
    return PerformanceReviewOutput.model_validate(
        {
            **_envelope(AgentRole.PERFORMANCE_REVIEWER, "output-performance"),
            "payload": PerformanceReviewResult(
                findings=("No performance claim is made",),
                recommendations=("Collect evidence",),
            ),
        }
    )


def stage_one_context() -> StageOneContext:
    return StageOneContext(
        market_context=market_context_output(),
        trend=trend_output(),
        price_action=price_action_output(),
    )
