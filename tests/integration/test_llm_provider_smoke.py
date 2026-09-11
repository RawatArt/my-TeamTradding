"""Explicit provider-specific M5 smoke tests; never enabled by CI or ordinary pytest."""

import asyncio
import json
import os
from collections.abc import Callable

import pytest
from pydantic import SecretStr

from ai_trading_team.config import AppSettings
from ai_trading_team.runtime.providers.anthropic.adapter import AnthropicAdapter
from ai_trading_team.runtime.providers.gemini.adapter import GeminiAdapter
from ai_trading_team.runtime.providers.openai.adapter import OpenAIAdapter
from ai_trading_team.schemas.enums import ModelProvider, ReasoningEffort
from ai_trading_team.schemas.runtime import ProviderRequest


def _enabled(name: str) -> bool:
    return os.getenv(name, "").casefold() in {"1", "true", "yes"}


@pytest.mark.llm_smoke
@pytest.mark.parametrize(
    ("provider", "flag", "model_variable", "key_getter", "adapter_factory"),
    [
        (
            ModelProvider.OPENAI,
            "RUN_OPENAI_SMOKE",
            "OPENAI_SMOKE_MODEL",
            lambda settings: settings.llm.openai_api_key,
            OpenAIAdapter,
        ),
        (
            ModelProvider.ANTHROPIC,
            "RUN_ANTHROPIC_SMOKE",
            "ANTHROPIC_SMOKE_MODEL",
            lambda settings: settings.llm.anthropic_api_key,
            AnthropicAdapter,
        ),
        (
            ModelProvider.GEMINI,
            "RUN_GEMINI_SMOKE",
            "GEMINI_SMOKE_MODEL",
            lambda settings: settings.llm.gemini_api_key,
            GeminiAdapter,
        ),
    ],
)
def test_provider_minimal_structured_output_smoke(
    provider: ModelProvider,
    flag: str,
    model_variable: str,
    key_getter: Callable[[AppSettings], SecretStr | None],
    adapter_factory: type[OpenAIAdapter | AnthropicAdapter | GeminiAdapter],
) -> None:
    settings = AppSettings()
    key = key_getter(settings)
    model = os.getenv(model_variable)
    if not _enabled(flag) or key is None or not model:
        pytest.skip(f"{provider.value} smoke requires explicit flag, credential, and model")

    adapter = adapter_factory(api_key=key)
    request = ProviderRequest(
        invocation_id=f"smoke-{provider.value.casefold()}",
        provider=provider,
        model_identifier=model,
        attempt=1,
        system_prompt="Return only JSON matching the supplied schema.",
        context_json='{"task":"Return ok=true. No trading task is present."}',
        output_json_schema=(
            '{"type":"object","properties":{"ok":{"type":"boolean"}},'
            '"required":["ok"],"additionalProperties":false}'
        ),
        max_output_tokens=32,
        timeout_seconds=30,
        reasoning_effort=ReasoningEffort.NONE,
    )

    response = asyncio.run(adapter.invoke(request))
    assert json.loads(response.response_json) == {"ok": True}
