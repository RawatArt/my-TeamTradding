import asyncio
import json
from datetime import timedelta
from decimal import Decimal

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.orchestration.identifiers import logical_invocation_id
from ai_trading_team.orchestration.runtime import (
    AgentRuntimeAssignment,
    RuntimeAgentInvoker,
)
from ai_trading_team.orchestration.shadow import ShadowCycleOrchestrator
from ai_trading_team.prompts import PromptRegistry
from ai_trading_team.risk import RiskEngine
from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry
from ai_trading_team.runtime.budget import BudgetGuard, InMemoryBudgetLedger
from ai_trading_team.runtime.router import RuntimeRouter
from ai_trading_team.schemas.agents import AgentDescriptor, AgentOutput, PromptReference
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentInvocationMode,
    AgentRole,
    MetricAvailability,
    ModelProvider,
    ReasoningEffort,
    ShadowDisposition,
    TokenEstimateMethod,
    TradeAction,
)
from ai_trading_team.schemas.runtime import (
    AIBudgetPolicy,
    InvocationUsage,
    ModelCapabilityProfile,
    PricingProfile,
    ProviderAdapterIdentity,
    ProviderRequest,
    ProviderResponse,
    RetryPolicy,
    RuntimeProfile,
    TokenEstimate,
    UsageValue,
)
from ai_trading_team.storage.shadow_audit import InMemoryShadowAuditRepository
from tests.fakes.agents import (
    chief_output,
    entry_output,
    market_context_output,
    price_action_output,
    skeptic_output,
    trend_output,
)
from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot


class RoleAwareFakeProvider:
    provider = ModelProvider.FAKE

    def __init__(self, bodies: dict[str, str]) -> None:
        self._bodies = bodies
        self.requests: list[ProviderRequest] = []

    def prepare(self) -> None:
        pass

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return TokenEstimate(
            tokens=100,
            method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
            conservative=True,
            estimated_at=EVALUATED_AT,
        )

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        reported = UsageValue(value=20, availability=MetricAvailability.REPORTED)
        return ProviderResponse(
            response_json=self._bodies[request.invocation_id],
            provider_request_id=f"request-{len(self.requests)}",
            model_identifier="fake-shadow-model",
            responded_at=EVALUATED_AT + timedelta(seconds=1),
            usage=InvocationUsage(input_tokens=reported, output_tokens=reported),
        )


def semantic_body(output: AgentOutput[CoreModel]) -> str:
    return json.dumps(
        {
            "confidence": str(output.confidence),
            "evidence": [item.model_dump(mode="json") for item in output.evidence],
            "warnings": [item.model_dump(mode="json") for item in output.warnings],
            "invalidations": [item.model_dump(mode="json") for item in output.invalidations],
            "payload": output.payload.model_dump(mode="json"),
        },
        separators=(",", ":"),
    )


def test_fake_provider_executes_full_typed_shadow_cycle_without_execution() -> None:
    snapshot = risk_snapshot()
    role_outputs = {
        AgentRole.MARKET_CONTEXT: market_context_output(),
        AgentRole.TREND_ANALYST: trend_output(),
        AgentRole.PRICE_ACTION_ANALYST: price_action_output(),
        AgentRole.ENTRY_ANALYST: entry_output(),
        AgentRole.SKEPTIC: skeptic_output(),
        AgentRole.CHIEF_TRADER: chief_output(TradeAction.BUY),
    }
    stage_for_role = {
        AgentRole.MARKET_CONTEXT: 1,
        AgentRole.TREND_ANALYST: 1,
        AgentRole.PRICE_ACTION_ANALYST: 1,
        AgentRole.ENTRY_ANALYST: 2,
        AgentRole.SKEPTIC: 4,
        AgentRole.CHIEF_TRADER: 5,
    }
    bodies = {
        logical_invocation_id(
            snapshot.cycle_id,
            snapshot.snapshot_id,
            stage,
            role,
            1 if stage in {4, 5} else None,
        ): semantic_body(output)  # type: ignore[arg-type]
        for role, output in role_outputs.items()
        for stage in (stage_for_role[role],)
    }
    provider = RoleAwareFakeProvider(bodies)
    prompts = PromptRegistry.default()
    runtime = RuntimeProfile(
        profile_ref="runtime-shadow-fake-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier="fake-shadow-model",
        request_timeout_seconds=10,
        total_timeout_seconds=20,
        max_output_tokens=1_000,
        reasoning_effort=ReasoningEffort.NONE,
        capability_profile_ref="capability-shadow-fake-v1",
        retry_policy_ref="retry-shadow-v1",
        cost_policy_ref="budget-shadow-v1",
        pricing_profile_ref="pricing-shadow-fake-v1",
    )
    capability = ModelCapabilityProfile(
        profile_ref="capability-shadow-fake-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier="fake-shadow-model",
        structured_output_supported=True,
        json_schema_supported=True,
        reasoning_configuration_supported=False,
        supported_reasoning_efforts=(ReasoningEffort.NONE,),
        max_context_tokens=50_000,
        max_output_tokens=2_000,
        token_estimation_methods=frozenset({TokenEstimateMethod.CONSERVATIVE_ESTIMATE}),
        adapter_contract_accepted=True,
    )
    retry = RetryPolicy(
        policy_ref="retry-shadow-v1", policy_version="1.0.0", max_attempts=1
    )
    budget = AIBudgetPolicy(
        policy_ref="budget-shadow-v1",
        policy_version="1.0.0",
        currency="USD",
        maximum_estimated_cost_per_call=Decimal("1"),
        daily_budget=Decimal("100"),
        monthly_budget=Decimal("1000"),
        maximum_calls_per_cycle=20,
        maximum_calls_per_day=100,
        maximum_input_tokens=10_000,
        maximum_output_tokens=2_000,
    )
    pricing = PricingProfile(
        profile_ref="pricing-shadow-fake-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier="fake-shadow-model",
        currency="USD",
        input_cost_per_million_tokens=Decimal("1"),
        output_cost_per_million_tokens=Decimal("1"),
        valid_from=EVALUATED_AT - timedelta(days=1),
    )
    prompt_ids = {
        AgentRole.MARKET_CONTEXT: "market-context",
        AgentRole.TREND_ANALYST: "trend-analyst",
        AgentRole.PRICE_ACTION_ANALYST: "price-action",
        AgentRole.ENTRY_ANALYST: "entry-analyst",
        AgentRole.SKEPTIC: "skeptic",
        AgentRole.CHIEF_TRADER: "chief-trader",
    }
    assignments = {}
    for role, prompt_id in prompt_ids.items():
        prompt = prompts.get(prompt_id, "1.0.0")
        assignments[role] = AgentRuntimeAssignment(
            descriptor=AgentDescriptor(
                agent_name=role.value.casefold(),
                role=role,
                agent_version="1.0.0",
                prompt_ref=PromptReference(
                    prompt_id=prompt.prompt_id,
                    prompt_version=prompt.prompt_version,
                    content_digest=prompt.content_digest,
                ),
                execution_profile=AgentExecutionProfile.REALTIME,
                runtime_profile_ref=runtime.profile_ref,
                invocation_mode=AgentInvocationMode.REALTIME,
                invocation_policy_ref="shadow-realtime-v1",
                cost_policy_ref=budget.policy_ref,
            ),
            runtime=runtime,
            capability=capability,
            retry_policy=retry,
            budget_policy=budget,
            pricing=pricing,
            adapter_identity=ProviderAdapterIdentity(
                provider=ModelProvider.FAKE,
                adapter_version="1.0.0",
                provider_sdk_version="not-applicable",
            ),
        )
    router = RuntimeRouter(
        prompts=prompts,
        providers={ModelProvider.FAKE: provider},
        budget=BudgetGuard(InMemoryBudgetLedger()),
    )
    orchestrator = ShadowCycleOrchestrator(
        invoker=RuntimeAgentInvoker(
            router, assignments, ProviderAcceptanceRegistry()
        ),
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=InMemoryShadowAuditRepository(),
        clock=lambda: EVALUATED_AT + timedelta(seconds=30),
    )

    record = asyncio.run(orchestrator.run_shadow_cycle(snapshot, account_context(snapshot)))

    assert record.decision_cycle.final_disposition is ShadowDisposition.WOULD_BUY
    assert record.shadow_trade_intent is not None
    assert len(provider.requests) == 6
    assert len({request.invocation_id for request in provider.requests}) == 6
