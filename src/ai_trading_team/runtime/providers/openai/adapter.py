"""OpenAI Responses adapter; the optional SDK import is isolated here."""

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


class OpenAITransport:
    def __init__(self, api_key: SecretStr) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            from ai_trading_team.runtime.errors import ProviderError
            from ai_trading_team.schemas.enums import RuntimeFailureCategory

            raise ProviderError(
                RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                "OpenAI SDK is not installed",
                retryable=False,
                dispatch_occurred=False,
            ) from exc
        self._client: Any = AsyncOpenAI(
            api_key=api_key.get_secret_value(),
            max_retries=0,
        )

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return conservative_byte_estimate(request)

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        schema = json.loads(request.output_json_schema)
        kwargs: dict[str, Any] = {
            "model": request.model_identifier,
            "instructions": request.system_prompt,
            "input": request.context_json,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
            "tools": [],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_semantic_body",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if request.reasoning_effort is not ReasoningEffort.NONE:
            kwargs["reasoning"] = {"effort": request.reasoning_effort.value.casefold()}
        try:
            response = await self._client.responses.create(**kwargs)
        except Exception as exc:
            raise classify_provider_exception(exc) from exc
        usage = field(response, "usage")
        input_details = field(usage, "input_tokens_details")
        output_details = field(usage, "output_tokens_details")
        return ProviderResponse(
            response_json=str(field(response, "output_text", "")),
            provider_request_id=field(response, "id"),
            model_identifier=str(field(response, "model", request.model_identifier)),
            responded_at=utc_now(),
            usage=reported_usage(
                input_tokens=field(usage, "input_tokens"),
                cached_input_tokens=field(input_details, "cached_tokens"),
                output_tokens=field(usage, "output_tokens"),
                reasoning_tokens=field(output_details, "reasoning_tokens"),
            ),
        )


class OpenAIAdapter(ProviderAdapterBase):
    provider = ModelProvider.OPENAI

    def _create_transport(self, api_key: SecretStr) -> ProviderTransport:
        return OpenAITransport(api_key)
