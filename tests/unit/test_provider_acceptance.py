from datetime import timedelta

import pytest
from tests.fakes.risk import EVALUATED_AT
from tests.fakes.runtime import capability_profile, runtime_profile

from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry, profile_digest
from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.enums import ModelProvider
from ai_trading_team.schemas.runtime import (
    ModelCapabilityProfile,
    ProviderAcceptanceRecord,
    ProviderAdapterIdentity,
    RuntimeProfile,
)


def real_profiles() -> tuple[RuntimeProfile, ModelCapabilityProfile, ProviderAdapterIdentity]:
    runtime = runtime_profile().model_copy(
        update={"provider": ModelProvider.OPENAI, "model_identifier": "accepted-model"}
    )
    capability = capability_profile().model_copy(
        update={
            "provider": ModelProvider.OPENAI,
            "model_identifier": "accepted-model",
            "live_smoke_accepted": True,
        }
    )
    identity = ProviderAdapterIdentity(
        provider=ModelProvider.OPENAI,
        adapter_version="1.0.0",
        provider_sdk_version="2.54.0",
    )
    return runtime, capability, identity


def accepted_record() -> ProviderAcceptanceRecord:
    runtime, capability, identity = real_profiles()
    return ProviderAcceptanceRecord(
        acceptance_id="openai-accepted-model-smoke-001",
        provider=runtime.provider,
        model_identifier=runtime.model_identifier,
        adapter_version=identity.adapter_version,
        provider_sdk_version=identity.provider_sdk_version,
        capability_profile_digest=profile_digest(
            capability, exclude={"live_smoke_accepted"}
        ),
        runtime_profile_digest=profile_digest(runtime),
        smoke_tested_at=EVALUATED_AT,
        smoke_result_id="smoke-result-001",
    )


def test_exact_provider_acceptance_record_is_eligible() -> None:
    runtime, capability, identity = real_profiles()
    record = accepted_record()

    assert ProviderAcceptanceRegistry([record]).require_eligible(
        runtime, capability, identity
    ) == record


@pytest.mark.parametrize(
    "change",
    [
        "adapter",
        "sdk",
        "capability",
        "runtime",
    ],
)
def test_stale_provider_acceptance_fails_closed(change: str) -> None:
    runtime, capability, identity = real_profiles()
    if change == "adapter":
        identity = identity.model_copy(update={"adapter_version": "2.0.0"})
    elif change == "sdk":
        identity = identity.model_copy(update={"provider_sdk_version": "2.55.0"})
    elif change == "capability":
        capability = capability.model_copy(update={"max_output_tokens": 1_999})
    else:
        runtime = runtime.model_copy(update={"total_timeout_seconds": 91})

    with pytest.raises(RuntimeInvocationError, match="stale or incompatible"):
        ProviderAcceptanceRegistry([accepted_record()]).require_eligible(
            runtime, capability, identity
        )


def test_acceptance_timestamp_is_timezone_aware_and_normalized() -> None:
    record = accepted_record().model_copy(
        update={"smoke_tested_at": EVALUATED_AT + timedelta(hours=7)}
    )
    restored = ProviderAcceptanceRecord.model_validate(record.model_dump())
    assert restored.smoke_tested_at.utcoffset() == timedelta(0)


def test_real_provider_without_acceptance_is_ineligible() -> None:
    runtime, capability, identity = real_profiles()
    with pytest.raises(RuntimeInvocationError, match="no recorded"):
        ProviderAcceptanceRegistry().require_eligible(runtime, capability, identity)
