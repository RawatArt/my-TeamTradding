"""Pre-dispatch compatibility and strict structured-output validation."""

import json
from decimal import Decimal
from typing import Any, cast

from pydantic import ValidationError

from ai_trading_team.runtime.contracts import RoleContract
from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.enums import (
    ModelProvider,
    ReasoningEffort,
    RuntimeFailureCategory,
)
from ai_trading_team.schemas.runtime import (
    AgentInvocationRequest,
    ModelCapabilityProfile,
    ModelGeneratedAgentBody,
    PromptArtifact,
    RuntimeProfile,
    TokenEstimate,
)


def validate_compatibility(
    request: AgentInvocationRequest,
    prompt: PromptArtifact,
    runtime: RuntimeProfile,
    capability: ModelCapabilityProfile,
    contract: RoleContract,
    estimate: TokenEstimate,
) -> None:
    """Reject unsupported or mismatched combinations before provider dispatch."""
    descriptor = request.descriptor
    if descriptor.prompt_ref.prompt_id != prompt.prompt_id or (
        descriptor.prompt_ref.prompt_version != prompt.prompt_version
    ):
        raise _incompatible("descriptor prompt reference does not match artifact")
    if descriptor.prompt_ref.content_digest != prompt.content_digest:
        raise _incompatible("descriptor prompt digest does not match artifact")
    if descriptor.role is not prompt.role:
        raise _incompatible("prompt role does not match agent role")
    if descriptor.runtime_profile_ref != runtime.profile_ref:
        raise _incompatible("descriptor runtime profile does not match requested profile")
    if runtime.capability_profile_ref != capability.profile_ref:
        raise _incompatible("runtime capability reference does not match validated profile")
    if runtime.provider is not capability.provider or (
        runtime.model_identifier != capability.model_identifier
    ):
        raise _incompatible("runtime provider/model does not match capability profile")
    if request.input_schema != prompt.compatible_input_schema or (
        request.output_schema != prompt.compatible_output_schema
    ):
        raise RuntimeInvocationError(
            RuntimeFailureCategory.SCHEMA_INCOMPATIBLE,
            "invocation schema references are incompatible with prompt artifact",
        )
    if not isinstance(request.context, contract.input_type):
        raise RuntimeInvocationError(
            RuntimeFailureCategory.SCHEMA_INCOMPATIBLE,
            "context type is incompatible with the role contract",
        )
    if runtime.require_structured_output and not capability.structured_output_supported:
        raise _incompatible("structured output is unsupported")
    if runtime.require_json_schema and not capability.json_schema_supported:
        raise _incompatible("JSON Schema output is unsupported")
    if runtime.max_output_tokens > capability.max_output_tokens:
        raise _incompatible("requested output limit exceeds model capability")
    if runtime.reasoning_effort is not ReasoningEffort.NONE and (
        not capability.reasoning_configuration_supported
        or runtime.reasoning_effort not in capability.supported_reasoning_efforts
    ):
        raise _incompatible("requested reasoning configuration is unsupported")
    if estimate.tokens is not None and (
        estimate.tokens + runtime.max_output_tokens > capability.max_context_tokens
    ):
        raise _incompatible("estimated request exceeds model context limit")
    if estimate.method not in capability.token_estimation_methods:
        raise _incompatible("token estimation method is not validated for this model")
    if not capability.adapter_contract_accepted:
        raise _incompatible("provider adapter contract has not been accepted")
    if capability.provider is not ModelProvider.FAKE and not capability.live_smoke_accepted:
        raise _incompatible("provider live smoke acceptance is required for runtime use")


def parse_model_body(
    response_json: str,
    contract: RoleContract,
) -> ModelGeneratedAgentBody[Any]:
    """Parse once without prose repair and preserve Decimal values from JSON numbers."""
    try:
        value = json.loads(response_json, parse_float=Decimal)
        _reject_binary_floats(value)
        body = contract.body_adapter.validate_python(value)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise RuntimeInvocationError(
            RuntimeFailureCategory.INVALID_MODEL_OUTPUT,
            "provider response failed strict structured-output validation",
        ) from exc
    return cast(ModelGeneratedAgentBody[Any], body)


def _reject_binary_floats(value: object) -> None:
    if isinstance(value, float):
        raise ValueError("binary float is forbidden at runtime boundaries")
    if isinstance(value, dict):
        for item in value.values():
            _reject_binary_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_binary_floats(item)


def _incompatible(detail: str) -> RuntimeInvocationError:
    return RuntimeInvocationError(RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE, detail)
