"""Deterministic M5 runtime fixtures with no network or provider SDK."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.prompts import PromptRegistry
from ai_trading_team.runtime.contracts import contract_for_role
from ai_trading_team.runtime.errors import ProviderError
from ai_trading_team.schemas.agents import AgentDescriptor, PromptReference
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentInvocationMode,
    AgentRole,
    MetricAvailability,
    ModelProvider,
    ReasoningEffort,
    TokenEstimateMethod,
    UsageMetric,
)
from ai_trading_team.schemas.orchestration import MarketContextInput
from ai_trading_team.schemas.runtime import (
    AgentInvocationRequest,
    AIBudgetPolicy,
    InvocationUsage,
    ModelCapabilityProfile,
    PricingProfile,
    ProviderRequest,
    ProviderResponse,
    RetryPolicy,
    RuntimeProfile,
    TokenEstimate,
    UsageValue,
)
from tests.fakes.agents import market_view
from tests.fakes.risk import CYCLE_ID, EVALUATED_AT, SNAPSHOT_ID

PROMPT_ID = "market-context"
RUNTIME_REF = "runtime-fake-v1"
MODEL_ID = "fake-structured-model"


def semantic_body(*, with_warning: bool = False) -> str:
    payload: dict[str, object] = {
        "confidence": "0.50",
        "evidence": [],
        "warnings": (
            [{"code": "limited-context", "message": "Optional evidence unavailable"}]
            if with_warning
            else []
        ),
        "invalidations": [],
        "payload": {"regime": "UNCERTAIN", "summary": "No clear market regime"},
    }
    return json.dumps(payload, separators=(",", ":"))


def reported(value: int) -> UsageValue:
    return UsageValue(value=value, availability=MetricAvailability.REPORTED)


class FakeProviderAdapter:
    provider = ModelProvider.FAKE

    def __init__(self, outcomes: list[ProviderResponse | ProviderError] | None = None) -> None:
        self.outcomes = outcomes or [provider_response()]
        self.invoke_count = 0
        self.prepare_count = 0
        self.requests: list[ProviderRequest] = []

    def prepare(self) -> None:
        self.prepare_count += 1

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return TokenEstimate(
            tokens=100,
            method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
            conservative=True,
            estimated_at=EVALUATED_AT,
        )

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        self.invoke_count += 1
        self.requests.append(request)
        outcome = self.outcomes[min(self.invoke_count - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def provider_response(body: str | None = None) -> ProviderResponse:
    return ProviderResponse(
        response_json=body or semantic_body(),
        provider_request_id="fake-request-001",
        model_identifier=MODEL_ID,
        responded_at=EVALUATED_AT + timedelta(seconds=1),
        usage=InvocationUsage(
            input_tokens=reported(90),
            cached_input_tokens=reported(0),
            output_tokens=reported(40),
            reasoning_tokens=reported(0),
        ),
    )


def prompt_registry() -> PromptRegistry:
    return PromptRegistry.default()


def invocation_request() -> AgentInvocationRequest:
    registry = prompt_registry()
    prompt = registry.get(PROMPT_ID, "1.0.0")
    context = MarketContextInput(
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        market=market_view(),
    )
    descriptor = AgentDescriptor(
        agent_name="market-context",
        role=AgentRole.MARKET_CONTEXT,
        agent_version="1.0.0",
        prompt_ref=PromptReference(
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.prompt_version,
            content_digest=prompt.content_digest,
        ),
        execution_profile=AgentExecutionProfile.REALTIME,
        runtime_profile_ref=RUNTIME_REF,
        invocation_mode=AgentInvocationMode.REALTIME,
        invocation_policy_ref="invocation-single-agent-v1",
        cost_policy_ref="budget-default",
    )
    return AgentInvocationRequest(
        invocation_id="invocation-m5-001",
        output_id="output-m5-001",
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        descriptor=descriptor,
        requested_at=EVALUATED_AT,
        input_schema=prompt.compatible_input_schema,
        output_schema=prompt.compatible_output_schema,
        context=context,
    )


def runtime_profile() -> RuntimeProfile:
    return RuntimeProfile(
        profile_ref=RUNTIME_REF,
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier=MODEL_ID,
        request_timeout_seconds=10,
        total_timeout_seconds=30,
        max_output_tokens=200,
        reasoning_effort=ReasoningEffort.NONE,
        capability_profile_ref="capability-fake-v1",
        retry_policy_ref="retry-bounded-v1",
        cost_policy_ref="budget-default",
        pricing_profile_ref="pricing-fake-v1",
    )


def retry_policy(*, max_attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(
        policy_ref="retry-bounded-v1",
        policy_version="1.0.0",
        max_attempts=max_attempts,
        retry_timeouts=True,
        retry_transient_errors=True,
        retry_rate_limits=False,
    )


def capability_profile() -> ModelCapabilityProfile:
    return ModelCapabilityProfile(
        profile_ref="capability-fake-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier=MODEL_ID,
        structured_output_supported=True,
        json_schema_supported=True,
        reasoning_configuration_supported=False,
        supported_reasoning_efforts=(ReasoningEffort.NONE,),
        max_context_tokens=10_000,
        max_output_tokens=2_000,
        usage_metrics=frozenset(UsageMetric),
        token_estimation_methods=frozenset({TokenEstimateMethod.CONSERVATIVE_ESTIMATE}),
        adapter_contract_accepted=True,
        live_smoke_accepted=False,
    )


def budget_policy() -> AIBudgetPolicy:
    return AIBudgetPolicy(
        policy_ref="budget-default",
        policy_version="1.0.0",
        currency="USD",
        maximum_estimated_cost_per_call=Decimal("1"),
        daily_budget=Decimal("5"),
        monthly_budget=Decimal("20"),
        maximum_calls_per_cycle=3,
        maximum_calls_per_day=10,
        maximum_input_tokens=5_000,
        maximum_output_tokens=1_000,
    )


def pricing_profile() -> PricingProfile:
    return PricingProfile(
        profile_ref="pricing-fake-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier=MODEL_ID,
        currency="USD",
        input_cost_per_million_tokens=Decimal("1"),
        output_cost_per_million_tokens=Decimal("2"),
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
    )


class SequenceClock:
    def __init__(self, start: datetime = EVALUATED_AT) -> None:
        self._current = start

    def __call__(self) -> datetime:
        value = self._current
        self._current += timedelta(milliseconds=1)
        return value


class MonotonicClock:
    def __init__(self) -> None:
        self._value = 0.0

    def __call__(self) -> float:
        value = self._value
        self._value += 0.001
        return value


def contract_schema_has_no_status() -> bool:
    schema = contract_for_role(AgentRole.MARKET_CONTEXT).body_adapter.json_schema()
    return "status" not in schema.get("properties", {})


RuntimeFactory = Callable[[], RuntimeProfile]
