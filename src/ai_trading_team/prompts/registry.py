"""Load and verify immutable prompt artifacts and their role schema bindings."""

import hashlib
import tomllib
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ai_trading_team.runtime.contracts import contract_for_role, schema_reference
from ai_trading_team.schemas.enums import AgentRole
from ai_trading_team.schemas.runtime import PromptArtifact


class PromptRegistryError(RuntimeError):
    """Raised when prompt metadata, content, or schema compatibility is invalid."""


class PromptRegistry:
    """Read-only verified registry keyed by prompt ID and semantic version."""

    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path.resolve()
        self._artifacts = self._load()

    @classmethod
    def default(cls) -> "PromptRegistry":
        return cls(Path(__file__).parent / "artifacts" / "manifest.toml")

    def get(self, prompt_id: str, prompt_version: str) -> PromptArtifact:
        try:
            return self._artifacts[(prompt_id, prompt_version)]
        except KeyError as exc:
            raise PromptRegistryError("prompt reference is not registered") from exc

    def _load(self) -> dict[tuple[str, str], PromptArtifact]:
        try:
            manifest = tomllib.loads(self._manifest_path.read_text(encoding="utf-8"))
            entries = TypeAdapter(list[dict[str, str]]).validate_python(manifest["prompts"])
        except (OSError, KeyError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise PromptRegistryError("prompt manifest is invalid") from exc

        artifacts: dict[tuple[str, str], PromptArtifact] = {}
        root = self._manifest_path.parent
        for entry in entries:
            try:
                role = AgentRole(entry["role"])
                content_path = (root / entry["file"]).resolve()
                content_path.relative_to(root)
                raw = content_path.read_bytes()
                if b"\r" in raw:
                    raise PromptRegistryError("prompt content must use LF line endings")
                content = raw.decode("utf-8")
                digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
                if digest != entry["content_digest"]:
                    raise PromptRegistryError("prompt content digest mismatch")
                contract = contract_for_role(role)
                artifact = PromptArtifact(
                    prompt_id=entry["prompt_id"],
                    prompt_version=entry["prompt_version"],
                    role=role,
                    content=content,
                    content_digest=digest,
                    compatible_input_schema=schema_reference(contract.input_type),
                    compatible_output_schema=schema_reference(contract.body_adapter),
                )
            except (KeyError, OSError, UnicodeDecodeError, ValueError) as exc:
                if isinstance(exc, PromptRegistryError):
                    raise
                raise PromptRegistryError("prompt artifact is invalid") from exc
            key = (artifact.prompt_id, artifact.prompt_version)
            if key in artifacts:
                raise PromptRegistryError("duplicate prompt identity")
            artifacts[key] = artifact
        return artifacts
