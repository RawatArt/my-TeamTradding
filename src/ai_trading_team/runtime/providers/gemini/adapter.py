"""Gemini adapter; the optional Google Gen AI SDK import is isolated here."""

import json
from typing import Any

from pydantic import SecretStr

from ai_trading_team.runtime.providers.base import (
    ProviderAdapterBase,
    ProviderTransport,
    classify_provider_exception,
    conservative_byte_estimate,
    field,
    reported_usage,
)
from ai_trading_team.schemas.enums import ModelProvider, ReasoningEffort
from ai_trading_team.schemas.runtime import ProviderRequest, ProviderResponse, TokenEstimate
from ai_trading_team.utils.time import utc_now


class GeminiTransport:
    def __init__(self, api_key: SecretStr) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            from ai_trading_team.runtime.errors import ProviderError
            from ai_trading_team.schemas.enums import RuntimeFailureCategory

            raise ProviderError(
                RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                "Google Gen AI SDK is not installed",
                retryable=False,
                dispatch_occurred=False,
            ) from exc
        self._client: Any = genai.Client(
            api_key=api_key.get_secret_value(),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return conservative_byte_estimate(request)

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        schema = json.loads(request.output_json_schema)
        config: dict[str, Any] = {
            "system_instruction": request.system_prompt,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
            "max_output_tokens": request.max_output_tokens,
        }
        if request.reasoning_effort is not ReasoningEffort.NONE:
            config["thinking_config"] = {
                "thinking_level": request.reasoning_effort.value.casefold()
            }
        try:
            response = await self._client.aio.models.generate_content(
                model=request.model_identifier,
                contents=request.context_json,
                config=config,
            )
        except Exception as exc:
            raise classify_provider_exception(exc) from exc
        usage = field(response, "usage_metadata")
        return ProviderResponse(
            response_json=str(field(response, "text", "")),
            provider_request_id=field(response, "response_id"),
            model_identifier=str(field(response, "model_version", request.model_identifier)),
            responded_at=utc_now(),
            usage=reported_usage(
                input_tokens=field(usage, "prompt_token_count"),
                cached_input_tokens=field(usage, "cached_content_token_count"),
                output_tokens=field(usage, "candidates_token_count"),
                reasoning_tokens=field(usage, "thoughts_token_count"),
            ),
        )


class GeminiAdapter(ProviderAdapterBase):
    provider = ModelProvider.GEMINI
    adapter_version = "1.0.0"

    def _create_transport(self, api_key: SecretStr) -> ProviderTransport:
        return GeminiTransport(api_key)
