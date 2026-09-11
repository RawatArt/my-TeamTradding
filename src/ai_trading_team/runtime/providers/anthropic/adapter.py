"""Anthropic Messages adapter; the optional SDK import is isolated here."""

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
from ai_trading_team.schemas.enums import ModelProvider
from ai_trading_team.schemas.runtime import ProviderRequest, ProviderResponse, TokenEstimate
from ai_trading_team.utils.time import utc_now


class AnthropicTransport:
    def __init__(self, api_key: SecretStr) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            from ai_trading_team.runtime.errors import ProviderError
            from ai_trading_team.schemas.enums import RuntimeFailureCategory

            raise ProviderError(
                RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                "Anthropic SDK is not installed",
                retryable=False,
                dispatch_occurred=False,
            ) from exc
        self._client: Any = AsyncAnthropic(
            api_key=api_key.get_secret_value(),
            max_retries=0,
        )

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        return conservative_byte_estimate(request)

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        schema = json.loads(request.output_json_schema)
        try:
            response = await self._client.messages.create(
                model=request.model_identifier,
                system=request.system_prompt,
                messages=[{"role": "user", "content": request.context_json}],
                max_tokens=request.max_output_tokens,
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as exc:
            raise classify_provider_exception(exc) from exc
        usage = field(response, "usage")
        structured = field(response, "structured_output")
        if structured is not None:
            response_json = json.dumps(structured, separators=(",", ":"), default=str)
        else:
            content = field(response, "content", [])
            first = content[0] if content else None
            response_json = str(field(first, "text", ""))
        return ProviderResponse(
            response_json=response_json,
            provider_request_id=field(response, "id"),
            model_identifier=str(field(response, "model", request.model_identifier)),
            responded_at=utc_now(),
            usage=reported_usage(
                input_tokens=field(usage, "input_tokens"),
                cached_input_tokens=field(usage, "cache_read_input_tokens"),
                output_tokens=field(usage, "output_tokens"),
                reasoning_tokens=None,
            ),
        )


class AnthropicAdapter(ProviderAdapterBase):
    provider = ModelProvider.ANTHROPIC
    adapter_version = "1.0.0"

    def _create_transport(self, api_key: SecretStr) -> ProviderTransport:
        return AnthropicTransport(api_key)
