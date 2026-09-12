"""Fail-closed symbol and real-provider eligibility policies for M9."""

import hashlib
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ai_trading_team.orchestration.runtime import AgentRuntimeAssignment
from ai_trading_team.prompts.registry import PromptRegistry
from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry, profile_digest
from ai_trading_team.runtime.contracts import (
    canonical_schema_json,
    contract_for_role,
    schema_reference,
)
from ai_trading_team.schemas.agents import AgentFeatureView, AgentMarketView
from ai_trading_team.schemas.common import AccountReference, ContentDigest
from ai_trading_team.schemas.enums import AgentRole, ModelProvider
from ai_trading_team.schemas.observation import (
    AcceptanceEvidenceReference,
    ContinuousProviderAcceptanceRecord,
    SymbolTimestampAcceptanceRecord,
)
from ai_trading_team.schemas.runtime import (
    ModelCapabilityProfile,
    PromptArtifact,
    ProviderAcceptanceRecord,
    ProviderAdapterIdentity,
    RuntimeProfile,
    SchemaReference,
)


class SymbolTimestampIneligible(ValueError):
    """Raised when source UTC semantics lack exact current acceptance."""


class ProviderConfigurationIneligible(ValueError):
    """Pre-dispatch configuration failure; this is not a provider outage."""


def feature_allowlist_digest() -> ContentDigest:
    """Digest the exact AgentFeatureView validation schema and allowlist version."""
    payload = {
        "allowlist_version": "1.0.0",
        "schema": AgentFeatureView.model_json_schema(mode="validation"),
    }
    encoded = canonical_schema_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class SymbolTimestampEligibilityRegistry:
    def __init__(self, records: Iterable[SymbolTimestampAcceptanceRecord] = ()) -> None:
        self._records = tuple(records)
        ids = tuple(item.acceptance_id for item in self._records)
        if len(ids) != len(set(ids)):
            raise ValueError("symbol timestamp acceptance identifiers must be unique")

    @classmethod
    def from_toml(cls, path: Path | str) -> "SymbolTimestampEligibilityRegistry":
        try:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
            records = TypeAdapter(list[SymbolTimestampAcceptanceRecord]).validate_python(
                data.get("acceptance", [])
            )
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ValueError("symbol timestamp acceptance registry is invalid") from exc
        return cls(records)

    def require_eligible(
        self,
        *,
        symbol: str,
        account_ref: AccountReference,
        adapter_version: str,
        at: datetime,
    ) -> SymbolTimestampAcceptanceRecord:
        moment = _utc(at)
        matches = tuple(
            item
            for item in self._records
            if item.symbol == symbol
            and item.account_ref == account_ref
            and item.adapter_version == adapter_version
            and item.tested_at <= moment < item.expires_at
        )
        if len(matches) != 1:
            raise SymbolTimestampIneligible(
                "symbol timestamp semantics lack one exact current acceptance"
            )
        return matches[0]


class ContinuousProviderEligibilityRegistry:
    """Require exact M5, M6, and M9 acceptance evidence before dispatch."""

    def __init__(
        self,
        records: Iterable[ContinuousProviderAcceptanceRecord] = (),
        *,
        m5_registry: ProviderAcceptanceRegistry | None = None,
    ) -> None:
        self._records = tuple(records)
        self._m5 = m5_registry or ProviderAcceptanceRegistry()
        ids = tuple(item.acceptance_id for item in self._records)
        if len(ids) != len(set(ids)):
            raise ValueError("continuous provider acceptance identifiers must be unique")

    @classmethod
    def from_toml(
        cls,
        path: Path | str,
        *,
        m5_registry: ProviderAcceptanceRegistry,
    ) -> "ContinuousProviderEligibilityRegistry":
        try:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
            records = TypeAdapter(
                list[ContinuousProviderAcceptanceRecord]
            ).validate_python(data.get("acceptance", []))
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ValueError("continuous provider acceptance registry is invalid") from exc
        return cls(records, m5_registry=m5_registry)

    def require_assignment(
        self,
        *,
        role: AgentRole,
        runtime: RuntimeProfile,
        capability: ModelCapabilityProfile,
        adapter: ProviderAdapterIdentity,
        prompt: PromptArtifact,
        input_schema: SchemaReference,
        output_schema: SchemaReference,
        m6_evidence: AcceptanceEvidenceReference,
        m9_evidence: AcceptanceEvidenceReference,
        at: datetime,
    ) -> ContinuousProviderAcceptanceRecord | None:
        if runtime.provider is ModelProvider.FAKE:
            if not capability.adapter_contract_accepted:
                raise ProviderConfigurationIneligible("fake adapter contract is not accepted")
            return None
        try:
            m5_record = self._m5.require_eligible(runtime, capability, adapter)
        except Exception as exc:
            raise ProviderConfigurationIneligible(
                "M5 provider acceptance is missing or incompatible"
            ) from exc
        if m5_record is None:
            raise ProviderConfigurationIneligible("real provider lacks M5 acceptance evidence")
        m5_evidence = _m5_evidence(m5_record)
        moment = _utc(at)
        matches = tuple(
            item
            for item in self._records
            if item.agent_role is role
            and item.provider is runtime.provider
            and item.model_identifier == runtime.model_identifier
            and item.adapter_version == adapter.adapter_version
            and item.provider_sdk_version == adapter.provider_sdk_version
            and item.capability_profile_digest
            == profile_digest(capability, exclude={"live_smoke_accepted"})
            and item.runtime_profile_digest == profile_digest(runtime)
            and item.prompt_digest == prompt.content_digest
            and item.input_schema_digest == input_schema.schema_digest
            and item.output_schema_digest == output_schema.schema_digest
            and item.feature_allowlist_version == "1.0.0"
            and item.feature_allowlist_digest == feature_allowlist_digest()
            and item.m5_live_smoke == m5_evidence
            and item.m6_full_shadow == m6_evidence
            and item.m9_feature_input == m9_evidence
            and item.accepted_at <= moment < item.expires_at
        )
        if len(matches) != 1:
            raise ProviderConfigurationIneligible(
                "M9 provider acceptance chain is missing, stale, ambiguous, or incompatible"
            )
        return matches[0]


class StaticCycleProviderEligibility:
    """Simple coordinator gate after assignments were validated by the exact registry."""

    def __init__(self, eligible: bool) -> None:
        self._eligible = eligible

    def require_eligible(self, market_view: AgentMarketView, *, at: datetime) -> None:
        _utc(at)
        if market_view.schema_version != "2.0.0" or market_view.features is None:
            raise ProviderConfigurationIneligible("M9 requires feature-enriched agent input")
        if not self._eligible:
            raise ProviderConfigurationIneligible("provider configuration is not eligible")


class ContinuousRuntimeProviderGate:
    """Preflight every role assignment before the M6 graph can dispatch once."""

    def __init__(
        self,
        *,
        assignments: Mapping[AgentRole, AgentRuntimeAssignment],
        required_roles: Sequence[AgentRole],
        prompts: PromptRegistry,
        registry: ContinuousProviderEligibilityRegistry,
        m6_evidence: AcceptanceEvidenceReference,
        m9_evidence: AcceptanceEvidenceReference,
    ) -> None:
        self._assignments = dict(assignments)
        self._required_roles = tuple(required_roles)
        self._prompts = prompts
        self._registry = registry
        self._m6_evidence = m6_evidence
        self._m9_evidence = m9_evidence

    def require_eligible(self, market_view: AgentMarketView, *, at: datetime) -> None:
        """Fail closed before dispatch if any cycle role lacks exact acceptance."""
        if (
            market_view.schema_version != "2.0.0"
            or market_view.features is None
            or market_view.agent_feature_view_digest != market_view.features.content_digest
        ):
            raise ProviderConfigurationIneligible(
                "M9 requires an intact feature-enriched agent input"
            )
        for role in self._required_roles:
            try:
                assignment = self._assignments[role]
                descriptor = assignment.descriptor
                if descriptor.role is not role:
                    raise ValueError("assignment role mismatch")
                if descriptor.prompt_ref.prompt_version != "2.0.0":
                    raise ValueError("M9 requires a feature-aware v2 prompt")
                prompt = self._prompts.get(
                    descriptor.prompt_ref.prompt_id,
                    descriptor.prompt_ref.prompt_version,
                )
                if descriptor.prompt_ref.content_digest != prompt.content_digest:
                    raise ValueError("descriptor prompt digest mismatch")
                contract = contract_for_role(role)
                self._registry.require_assignment(
                    role=role,
                    runtime=assignment.runtime,
                    capability=assignment.capability,
                    adapter=assignment.adapter_identity,
                    prompt=prompt,
                    input_schema=schema_reference(contract.input_type),
                    output_schema=schema_reference(contract.body_adapter),
                    m6_evidence=self._m6_evidence,
                    m9_evidence=self._m9_evidence,
                    at=at,
                )
            except ProviderConfigurationIneligible:
                raise
            except Exception as exc:
                raise ProviderConfigurationIneligible(
                    "required role assignment is missing or incompatible"
                ) from exc


def _m5_evidence(record: ProviderAcceptanceRecord) -> AcceptanceEvidenceReference:
    return AcceptanceEvidenceReference(
        acceptance_id=record.acceptance_id,
        evidence_digest=profile_digest(record),
        accepted_at=record.smoke_tested_at,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("eligibility time must be timezone-aware")
    return value.astimezone(UTC)
