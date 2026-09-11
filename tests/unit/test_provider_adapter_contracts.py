import asyncio

import pytest
from pydantic import SecretStr
from tests.fakes.runtime import provider_response

from ai_trading_team.runtime.providers.anthropic.adapter import AnthropicAdapter
from ai_trading_team.runtime.providers.base import ProviderTransport, conservative_byte_estimate
from ai_trading_team.runtime.providers.gemini.adapter import GeminiAdapter
from ai_trading_team.runtime.providers.openai.adapter import OpenAIAdapter
from ai_trading_team.schemas.enums import ModelProvider, ReasoningEffort, TokenEstimateMethod
from ai_trading_team.schemas.runtime import ProviderRequest, ProviderResponse, TokenEstimate
from ai_trading_team.utils.time import utc_now


class FakeTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return TokenEstimate(
            tokens=10,
            method=TokenEstimateMethod.PROVIDER_TOKENIZER,
            conservative=True,
            estimated_at=utc_now(),
        )

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        return provider_response()


@pytest.mark.parametrize(
    ("adapter_type", "provider"),
    [
        (OpenAIAdapter, ModelProvider.OPENAI),
        (AnthropicAdapter, ModelProvider.ANTHROPIC),
        (GeminiAdapter, ModelProvider.GEMINI),
    ],
)
def test_all_provider_adapters_pass_same_fake_contract_suite(
    adapter_type: type[OpenAIAdapter | AnthropicAdapter | GeminiAdapter],
    provider: ModelProvider,
) -> None:
    transport = FakeTransport()
    adapter = adapter_type(api_key=SecretStr("not-a-real-key"), transport=transport)
    adapter.prepare()
    request = ProviderRequest(
        invocation_id="provider-contract-001",
        provider=provider,
        model_identifier="contract-test-model",
        attempt=1,
        system_prompt="Return structured test data only.",
        context_json="{}",
        output_json_schema='{"type":"object"}',
        max_output_tokens=32,
        timeout_seconds=5,
        reasoning_effort=ReasoningEffort.NONE,
    )

    estimate = asyncio.run(adapter.estimate_input_tokens(request))
    response = asyncio.run(adapter.invoke(request))

    assert estimate.method is TokenEstimateMethod.PROVIDER_TOKENIZER
    assert response.response_json
    assert transport.calls == 1


def test_provider_adapter_rejects_wrong_provider_before_transport() -> None:
    transport: ProviderTransport = FakeTransport()
    adapter = OpenAIAdapter(transport=transport)
    request = ProviderRequest(
        invocation_id="provider-contract-wrong",
        provider=ModelProvider.ANTHROPIC,
        model_identifier="contract-test-model",
        attempt=1,
        system_prompt="Structured output only.",
        context_json="{}",
        output_json_schema='{"type":"object"}',
        max_output_tokens=32,
        timeout_seconds=5,
        reasoning_effort=ReasoningEffort.NONE,
    )

    with pytest.raises(Exception, match="does not match"):
        asyncio.run(adapter.invoke(request))


def test_default_byte_estimate_is_explicitly_conservative() -> None:
    request = ProviderRequest(
        invocation_id="provider-estimate-001",
        provider=ModelProvider.OPENAI,
        model_identifier="contract-test-model",
        attempt=1,
        system_prompt="Structured output only.",
        context_json="{}",
        output_json_schema='{"type":"object"}',
        max_output_tokens=32,
        timeout_seconds=5,
        reasoning_effort=ReasoningEffort.NONE,
    )

    estimate = conservative_byte_estimate(request)
    assert estimate.conservative is True
    assert estimate.method is TokenEstimateMethod.CONSERVATIVE_ESTIMATE
    assert estimate.tokens is not None
