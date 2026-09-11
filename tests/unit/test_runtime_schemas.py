from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError
from tests.fakes.runtime import (
    capability_profile,
    invocation_request,
    prompt_registry,
    retry_policy,
    runtime_profile,
    semantic_body,
)

from ai_trading_team.runtime.contracts import contract_for_role
from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.runtime.validation import validate_compatibility
from ai_trading_team.schemas.agents import MarketContextResult
from ai_trading_team.schemas.enums import (
    AgentRole,
    MarketRegime,
    ModelProvider,
    RuntimeFailureCategory,
    TokenEstimateMethod,
)
from ai_trading_team.schemas.runtime import ModelGeneratedAgentBody, TokenEstimate


def test_model_generated_body_cannot_declare_runtime_status() -> None:
    payload = {
        "status": "SUCCESS",
        "confidence": "0.50",
        "payload": {"regime": "UNCERTAIN", "summary": "No clear regime"},
    }

    with pytest.raises(ValidationError, match="status"):
        TypeAdapter(ModelGeneratedAgentBody[MarketContextResult]).validate_python(payload)


def test_model_generated_body_preserves_decimal_through_json_boundary() -> None:
    body = TypeAdapter(ModelGeneratedAgentBody[MarketContextResult]).validate_json(semantic_body())
    restored = TypeAdapter(ModelGeneratedAgentBody[MarketContextResult]).validate_json(
        body.model_dump_json()
    )

    assert isinstance(restored.confidence, Decimal)
    assert restored.confidence == Decimal("0.50")
    assert restored.payload.regime is MarketRegime.UNCERTAIN


def test_runtime_profile_enforces_three_total_attempt_hard_limit() -> None:
    payload = retry_policy().model_dump(mode="python")
    payload["max_attempts"] = 4

    with pytest.raises(ValidationError):
        type(retry_policy()).model_validate(payload)


def test_capability_profile_is_separate_from_requested_runtime_profile() -> None:
    runtime = runtime_profile()
    capability = capability_profile()

    assert runtime.capability_profile_ref == capability.profile_ref
    assert "structured_output_supported" not in type(runtime).model_fields
    assert "request_timeout_seconds" not in type(capability).model_fields


def test_unavailable_token_estimate_cannot_carry_a_value() -> None:
    with pytest.raises(ValidationError):
        TokenEstimate(
            tokens=1,
            method=TokenEstimateMethod.UNAVAILABLE,
            conservative=False,
            estimated_at=datetime.now(UTC),
        )


def test_real_provider_is_ineligible_until_its_live_smoke_is_accepted() -> None:
    request = invocation_request()
    prompt = prompt_registry().get("market-context", "1.0.0")
    runtime = runtime_profile().model_copy(
        update={"provider": ModelProvider.OPENAI, "model_identifier": "model-under-test"}
    )
    capability = capability_profile().model_copy(
        update={
            "provider": ModelProvider.OPENAI,
            "model_identifier": "model-under-test",
            "live_smoke_accepted": False,
        }
    )
    estimate = TokenEstimate(
        tokens=100,
        method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
        conservative=True,
        estimated_at=datetime.now(UTC),
    )

    with pytest.raises(RuntimeInvocationError) as exc_info:
        validate_compatibility(
            request,
            prompt,
            runtime,
            capability,
            contract_for_role(AgentRole.MARKET_CONTEXT),
            estimate,
        )
    assert exc_info.value.category is RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE
    assert "live smoke" in str(exc_info.value)
