"""Fail-closed provider/model live-smoke acceptance registry."""

import hashlib
import tomllib
from collections.abc import Iterable
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ai_trading_team.runtime.contracts import canonical_schema_json
from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.common import ContentDigest, CoreModel
from ai_trading_team.schemas.enums import ModelProvider, RuntimeFailureCategory
from ai_trading_team.schemas.runtime import (
    ModelCapabilityProfile,
    ProviderAcceptanceRecord,
    ProviderAdapterIdentity,
    RuntimeProfile,
)


def profile_digest(profile: CoreModel, *, exclude: set[str] | None = None) -> ContentDigest:
    """Return a deterministic digest of trusted profile fields."""
    payload = profile.model_dump(mode="json", exclude=exclude)
    encoded = canonical_schema_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class ProviderAcceptanceRegistry:
    """Require an exact, current acceptance record before any real-provider dispatch."""

    def __init__(self, records: Iterable[ProviderAcceptanceRecord] = ()) -> None:
        self._records = tuple(records)
        keys = tuple(item.acceptance_id for item in self._records)
        if len(keys) != len(set(keys)):
            raise ValueError("provider acceptance identifiers must be unique")

    @classmethod
    def from_toml(cls, path: Path | str) -> "ProviderAcceptanceRegistry":
        """Load validated non-secret acceptance evidence from an explicit TOML file."""
        try:
            data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
            records = TypeAdapter(list[ProviderAcceptanceRecord]).validate_python(
                data.get("acceptance", [])
            )
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ValueError("provider acceptance registry is invalid") from exc
        return cls(records)

    def require_eligible(
        self,
        runtime: RuntimeProfile,
        capability: ModelCapabilityProfile,
        adapter: ProviderAdapterIdentity,
    ) -> ProviderAcceptanceRecord | None:
        """Return matching evidence, bypassing live-smoke evidence only for the fake provider."""
        if runtime.provider is ModelProvider.FAKE:
            if not capability.adapter_contract_accepted:
                raise self._ineligible("fake adapter contract has not been accepted")
            return None

        if not capability.adapter_contract_accepted or not capability.live_smoke_accepted:
            raise self._ineligible("provider capability profile lacks accepted smoke evidence")

        expected_capability = profile_digest(
            capability,
            exclude={"live_smoke_accepted"},
        )
        expected_runtime = profile_digest(runtime)
        candidates = tuple(
            item
            for item in self._records
            if item.provider is runtime.provider
            and item.model_identifier == runtime.model_identifier
        )
        match = next(
            (
                item
                for item in candidates
                if item.adapter_version == adapter.adapter_version
                and item.provider_sdk_version == adapter.provider_sdk_version
                and item.capability_profile_digest == expected_capability
                and item.runtime_profile_digest == expected_runtime
            ),
            None,
        )
        if match is None:
            detail = (
                "provider/model has no recorded live-smoke acceptance"
                if not candidates
                else "provider live-smoke acceptance is stale or incompatible"
            )
            raise self._ineligible(detail)
        if adapter.provider is not runtime.provider:
            raise self._ineligible("provider adapter identity is incompatible")
        return match

    @staticmethod
    def _ineligible(detail: str) -> RuntimeInvocationError:
        return RuntimeInvocationError(RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE, detail)
