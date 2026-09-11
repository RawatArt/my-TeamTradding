"""Explicit real-provider M6 SHADOW test; ordinary and CI runs always skip it."""

import asyncio
import importlib.metadata
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from ai_trading_team.config import AppSettings, RiskConstitutionSettings
from ai_trading_team.orchestration.runtime import AgentRuntimeAssignment, RuntimeAgentInvoker
from ai_trading_team.orchestration.shadow import ShadowCycleOrchestrator
from ai_trading_team.prompts import PromptRegistry
from ai_trading_team.risk import RiskEngine
from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry
from ai_trading_team.runtime.budget import BudgetGuard, InMemoryBudgetLedger
from ai_trading_team.runtime.providers.anthropic.adapter import AnthropicAdapter
from ai_trading_team.runtime.providers.gemini.adapter import GeminiAdapter
from ai_trading_team.runtime.providers.openai.adapter import OpenAIAdapter
from ai_trading_team.runtime.router import RuntimeRouter
from ai_trading_team.schemas.agents import AgentDescriptor, PromptReference
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentInvocationMode,
    AgentRole,
    ModelProvider,
    ShadowDisposition,
)
from ai_trading_team.schemas.runtime import (
    AIBudgetPolicy,
    ModelCapabilityProfile,
    PricingProfile,
    ProviderAdapterIdentity,
    RetryPolicy,
    RuntimeProfile,
)
from ai_trading_team.storage.shadow_audit import InMemoryShadowAuditRepository
from tests.fakes.risk import account_context, risk_snapshot


def _enabled() -> bool:
    return os.getenv("RUN_M6_PROVIDER_SHADOW", "").casefold() in {"1", "true", "yes"}


@pytest.mark.shadow_provider
def test_explicit_accepted_provider_builds_one_complete_shadow_record() -> None:
    config_path = os.getenv("M6_SHADOW_PROVIDER_CONFIG")
    acceptance_path = os.getenv("M6_PROVIDER_ACCEPTANCE_FILE")
    if not _enabled() or not config_path or not acceptance_path:
        pytest.skip("M6 provider SHADOW test requires explicit flag and both config paths")
    data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    runtime = RuntimeProfile.model_validate(data["runtime"])
    capability = ModelCapabilityProfile.model_validate(data["capability"])
    retry = RetryPolicy.model_validate(data["retry"])
    budget = AIBudgetPolicy.model_validate(data["budget"])
    pricing = PricingProfile.model_validate(data["pricing"])
    settings = AppSettings()
    adapter_types = {
        ModelProvider.OPENAI: OpenAIAdapter,
        ModelProvider.ANTHROPIC: AnthropicAdapter,
        ModelProvider.GEMINI: GeminiAdapter,
    }
    secrets = {
        ModelProvider.OPENAI: settings.llm.openai_api_key,
        ModelProvider.ANTHROPIC: settings.llm.anthropic_api_key,
        ModelProvider.GEMINI: settings.llm.gemini_api_key,
    }
    key: SecretStr | None = secrets.get(runtime.provider)
    adapter_type = adapter_types.get(runtime.provider)
    if key is None or adapter_type is None:
        pytest.skip("selected provider credential is not explicitly configured")
    adapter = adapter_type(api_key=key)
    acceptance = ProviderAcceptanceRegistry.from_toml(acceptance_path)
    identity = ProviderAdapterIdentity(
        provider=runtime.provider,
        adapter_version=adapter.adapter_version,
        provider_sdk_version=importlib.metadata.version(
            {
                ModelProvider.OPENAI: "openai",
                ModelProvider.ANTHROPIC: "anthropic",
                ModelProvider.GEMINI: "google-genai",
            }[runtime.provider]
        ),
    )
    prompts = PromptRegistry.default()
    prompt_ids = {
        AgentRole.MARKET_CONTEXT: "market-context",
        AgentRole.TREND_ANALYST: "trend-analyst",
        AgentRole.PRICE_ACTION_ANALYST: "price-action",
        AgentRole.ENTRY_ANALYST: "entry-analyst",
        AgentRole.SKEPTIC: "skeptic",
        AgentRole.CHIEF_TRADER: "chief-trader",
    }
    assignments: dict[AgentRole, AgentRuntimeAssignment] = {}
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
                invocation_policy_ref="m6-shadow-provider-v1",
                cost_policy_ref=budget.policy_ref,
            ),
            runtime=runtime,
            capability=capability,
            retry_policy=retry,
            budget_policy=budget,
            pricing=pricing,
            adapter_identity=identity,
        )
    router = RuntimeRouter(
        prompts=prompts,
        providers={runtime.provider: adapter},
        budget=BudgetGuard(InMemoryBudgetLedger()),
    )
    snapshot = risk_snapshot()
    orchestrator = ShadowCycleOrchestrator(
        invoker=RuntimeAgentInvoker(router, assignments, acceptance),
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=InMemoryShadowAuditRepository(),
        clock=lambda: datetime.now(UTC),
    )

    record = asyncio.run(orchestrator.run_shadow_cycle(snapshot, account_context(snapshot)))

    assert record.decision_cycle.agent_failures == ()
    assert record.decision_cycle.chief_decision is not None
    assert record.decision_cycle.final_disposition in {
        ShadowDisposition.CHIEF_HOLD,
        ShadowDisposition.WOULD_BUY,
        ShadowDisposition.WOULD_SELL,
        ShadowDisposition.RISK_REJECTED,
        ShadowDisposition.RISK_HALTED,
    }
