"""Shared adapter mechanics; no vendor SDK is imported here."""

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import SecretStr

from ai_trading_team.runtime.errors import ProviderError
from ai_trading_team.schemas.enums import (
    MetricAvailability,
    ModelProvider,
    RuntimeFailureCategory,
    TokenEstimateMethod,
)
from ai_trading_team.schemas.runtime import (
    InvocationUsage,
    ProviderRequest,
    ProviderResponse,
    TokenEstimate,
    UsageValue,
)


class ProviderTransport(Protocol):
    """Provider-package transport normalized before leaving the adapter."""

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate: ...

    async def invoke(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderAdapterBase:
    """Validate provider identity and delegate only to an isolated transport."""

    provider: ModelProvider

    def __init__(
        self,
        *,
        api_key: SecretStr | None = None,
        transport: ProviderTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._transport = transport

    def prepare(self) -> None:
        """Resolve credentials/SDK availability without making a provider request."""
        self._get_transport()

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        self._validate_request(request)
        transport = self._get_transport()
        return await transport.estimate_input_tokens(request)

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        self._validate_request(request)
        transport = self._get_transport()
        try:
            import asyncio

            return await asyncio.wait_for(
                transport.invoke(request),
                timeout=float(request.timeout_seconds),
            )
        except ProviderError:
            raise
        except TimeoutError as exc:
            raise ProviderError(
                RuntimeFailureCategory.PROVIDER_TIMEOUT,
                "provider request timed out",
                retryable=True,
                dispatch_occurred=True,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                RuntimeFailureCategory.UNKNOWN_PROVIDER_ERROR,
                "provider request failed",
                retryable=False,
                dispatch_occurred=True,
            ) from exc

    def _get_transport(self) -> ProviderTransport:
        if self._transport is None:
            if self._api_key is None or not self._api_key.get_secret_value():
                raise ProviderError(
                    RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                    "provider credentials are not configured",
                    retryable=False,
                    dispatch_occurred=False,
                )
            self._transport = self._create_transport(self._api_key)
        return self._transport

    def _create_transport(self, api_key: SecretStr) -> ProviderTransport:
        raise NotImplementedError

    def _validate_request(self, request: ProviderRequest) -> None:
        if request.provider is not self.provider:
            raise ProviderError(
                RuntimeFailureCategory.INVALID_REQUEST,
                "request provider does not match adapter",
                retryable=False,
                dispatch_occurred=False,
            )


def unavailable_estimate() -> TokenEstimate:
    return TokenEstimate(
        tokens=None,
        method=TokenEstimateMethod.UNAVAILABLE,
        conservative=False,
        estimated_at=datetime.now(UTC),
    )


def conservative_byte_estimate(request: ProviderRequest) -> TokenEstimate:
    """Return an explicit upper-biased heuristic, never an exact token claim.

    The estimate reserves twice the UTF-8 byte count plus a fixed 512-token envelope allowance.
    It intentionally over-reserves and should be replaced by a validated provider tokenizer where
    available.
    """
    material = request.system_prompt + request.context_json + request.output_json_schema
    tokens = len(material.encode("utf-8")) * 2 + 512
    return TokenEstimate(
        tokens=tokens,
        method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
        conservative=True,
        estimated_at=datetime.now(UTC),
    )


def reported_usage(
    *,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None,
) -> InvocationUsage:

    def item(value: int | None) -> UsageValue:
        return UsageValue(
            value=value,
            availability=(
                MetricAvailability.REPORTED
                if value is not None
                else MetricAvailability.UNAVAILABLE
            ),
        )

    return InvocationUsage(
        input_tokens=item(input_tokens),
        cached_input_tokens=item(cached_input_tokens),
        output_tokens=item(output_tokens),
        reasoning_tokens=item(reasoning_tokens),
    )


def field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def classify_provider_exception(exc: Exception) -> ProviderError:
    """Map common SDK status/name signals without exposing exception text."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__.casefold()
    if status == 401 or "authentication" in name:
        category = RuntimeFailureCategory.PROVIDER_AUTHENTICATION
        retryable = False
    elif status == 403 or "permission" in name:
        category = RuntimeFailureCategory.PROVIDER_PERMISSION
        retryable = False
    elif status == 429 or "ratelimit" in name or "resourceexhausted" in name:
        category = RuntimeFailureCategory.PROVIDER_RATE_LIMIT
        retryable = True
    elif status in {408, 504} or "timeout" in name:
        category = RuntimeFailureCategory.PROVIDER_TIMEOUT
        retryable = True
    elif isinstance(status, int) and status >= 500:
        category = RuntimeFailureCategory.PROVIDER_TRANSIENT
        retryable = True
    else:
        category = RuntimeFailureCategory.UNKNOWN_PROVIDER_ERROR
        retryable = False
    return ProviderError(
        category,
        "provider request failed with a sanitized error",
        retryable=retryable,
        dispatch_occurred=True,
    )
