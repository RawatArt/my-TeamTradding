"""Exact M5 to M6 to M9 provider acceptance-chain tests."""

from datetime import timedelta

import pytest
from tests.fakes.risk import EVALUATED_AT
from tests.fakes.runtime import capability_profile, runtime_profile

from ai_trading_team.observation.eligibility import (
    ContinuousProviderEligibilityRegistry,
    ProviderConfigurationIneligible,
    feature_allowlist_digest,
)
from ai_trading_team.prompts import PromptRegistry
from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry, profile_digest
from ai_trading_team.runtime.contracts import contract_for_role, schema_reference
from ai_trading_team.schemas.enums import AgentRole, ModelProvider
from ai_trading_team.schemas.observation import (
    AcceptanceEvidenceReference,
    ContinuousProviderAcceptanceRecord,
)
from ai_trading_team.schemas.runtime import (
    ModelCapabilityProfile,
    PromptArtifact,
    ProviderAcceptanceRecord,
    ProviderAdapterIdentity,
    RuntimeProfile,
    SchemaReference,
)


def _inputs() -> tuple[
    RuntimeProfile,
    ModelCapabilityProfile,
    ProviderAdapterIdentity,
    PromptArtifact,
    SchemaReference,
    SchemaReference,
    ProviderAcceptanceRecord,
    AcceptanceEvidenceReference,
    AcceptanceEvidenceReference,
    ContinuousProviderAcceptanceRecord,
]:
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
    adapter = ProviderAdapterIdentity(
        provider=ModelProvider.OPENAI,
        adapter_version="1.0.0",
        provider_sdk_version="2.54.0",
    )
    prompt = PromptRegistry.default().get("market-context", "2.0.0")
    contract = contract_for_role(AgentRole.MARKET_CONTEXT)
    input_schema = schema_reference(contract.input_type)
    output_schema = schema_reference(contract.body_adapter)
    m5 = ProviderAcceptanceRecord(
        acceptance_id="m5-openai-accepted-model",
        provider=ModelProvider.OPENAI,
        model_identifier="accepted-model",
        adapter_version=adapter.adapter_version,
        provider_sdk_version=adapter.provider_sdk_version,
        capability_profile_digest=profile_digest(
            capability, exclude={"live_smoke_accepted"}
        ),
        runtime_profile_digest=profile_digest(runtime),
        smoke_tested_at=EVALUATED_AT - timedelta(days=3),
        smoke_result_id="m5-smoke-result",
    )
    m5_ref = AcceptanceEvidenceReference(
        acceptance_id=m5.acceptance_id,
        evidence_digest=profile_digest(m5),
        accepted_at=m5.smoke_tested_at,
    )
    m6_ref = AcceptanceEvidenceReference(
        acceptance_id="m6-shadow-acceptance",
        evidence_digest="sha256:" + "6" * 64,
        accepted_at=EVALUATED_AT - timedelta(days=2),
    )
    m9_ref = AcceptanceEvidenceReference(
        acceptance_id="m9-feature-acceptance",
        evidence_digest="sha256:" + "9" * 64,
        accepted_at=EVALUATED_AT - timedelta(days=1),
    )
    record = ContinuousProviderAcceptanceRecord(
        acceptance_id="m9-openai-continuous-acceptance",
        agent_role=AgentRole.MARKET_CONTEXT,
        provider=ModelProvider.OPENAI,
        model_identifier="accepted-model",
        adapter_version=adapter.adapter_version,
        provider_sdk_version=adapter.provider_sdk_version,
        capability_profile_digest=m5.capability_profile_digest,
        runtime_profile_digest=m5.runtime_profile_digest,
        prompt_digest=prompt.content_digest,
        input_schema_digest=input_schema.schema_digest,
        output_schema_digest=output_schema.schema_digest,
        feature_allowlist_version="1.0.0",
        feature_allowlist_digest=feature_allowlist_digest(),
        m5_live_smoke=m5_ref,
        m6_full_shadow=m6_ref,
        m9_feature_input=m9_ref,
        accepted_at=EVALUATED_AT - timedelta(hours=1),
        expires_at=EVALUATED_AT + timedelta(days=1),
    )
    return (
        runtime,
        capability,
        adapter,
        prompt,
        input_schema,
        output_schema,
        m5,
        m6_ref,
        m9_ref,
        record,
    )


@pytest.mark.parametrize(
    ("target", "field", "replacement"),
    [
        ("adapter", "provider_sdk_version", "2.55.0"),
        ("runtime", "total_timeout_seconds", 31),
        ("capability", "max_output_tokens", 1999),
        ("record", "prompt_digest", "sha256:" + "0" * 64),
        ("record", "input_schema_digest", "sha256:" + "1" * 64),
        ("record", "output_schema_digest", "sha256:" + "2" * 64),
        ("record", "feature_allowlist_digest", "sha256:" + "3" * 64),
        (
            "record",
            "m6_full_shadow",
            AcceptanceEvidenceReference(
                acceptance_id="wrong-m6",
                evidence_digest="sha256:" + "4" * 64,
                accepted_at=EVALUATED_AT - timedelta(days=2),
            ),
        ),
        (
            "record",
            "m9_feature_input",
            AcceptanceEvidenceReference(
                acceptance_id="wrong-m9",
                evidence_digest="sha256:" + "5" * 64,
                accepted_at=EVALUATED_AT - timedelta(days=1),
            ),
        ),
    ],
)
def test_any_stale_acceptance_chain_binding_fails_closed(
    target: str,
    field: str,
    replacement: object,
) -> None:
    runtime, capability, adapter, prompt, input_schema, output_schema, m5, m6, m9, record = (
        _inputs()
    )
    if target == "runtime":
        runtime = runtime.model_copy(update={field: replacement})
    elif target == "capability":
        capability = capability.model_copy(update={field: replacement})
    elif target == "adapter":
        adapter = adapter.model_copy(update={field: replacement})
    else:
        record = record.model_copy(update={field: replacement})
    registry = ContinuousProviderEligibilityRegistry(
        (record,),
        m5_registry=ProviderAcceptanceRegistry((m5,)),
    )

    with pytest.raises(ProviderConfigurationIneligible):
        registry.require_assignment(
            role=AgentRole.MARKET_CONTEXT,
            runtime=runtime,
            capability=capability,
            adapter=adapter,
            prompt=prompt,
            input_schema=input_schema,
            output_schema=output_schema,
            m6_evidence=m6,
            m9_evidence=m9,
            at=EVALUATED_AT,
        )
