import hashlib
from pathlib import Path

import pytest
from tests.fakes.runtime import prompt_registry

from ai_trading_team.prompts import PromptRegistry, PromptRegistryError
from ai_trading_team.schemas.enums import AgentRole


def test_default_registry_loads_all_nine_versioned_role_prompts() -> None:
    registry = prompt_registry()
    refs = {
        AgentRole.MARKET_CONTEXT: "market-context",
        AgentRole.TREND_ANALYST: "trend-analyst",
        AgentRole.PRICE_ACTION_ANALYST: "price-action",
        AgentRole.ENTRY_ANALYST: "entry-analyst",
        AgentRole.QUANT_RESEARCHER: "quant-researcher",
        AgentRole.SENIOR_QUANT_DEVELOPER: "senior-quant-developer",
        AgentRole.SKEPTIC: "skeptic",
        AgentRole.CHIEF_TRADER: "chief-trader",
        AgentRole.PERFORMANCE_REVIEWER: "performance-reviewer",
    }

    for role, prompt_id in refs.items():
        artifact = registry.get(prompt_id, "1.0.0")
        assert artifact.role is role
        assert artifact.content_digest.startswith("sha256:")
        assert artifact.compatible_input_schema.schema_digest.startswith("sha256:")
        assert artifact.compatible_output_schema.schema_digest.startswith("sha256:")


def test_registry_rejects_tampered_prompt_content(tmp_path: Path) -> None:
    content = b"trusted content\n"
    (tmp_path / "prompt.md").write_bytes(content)
    wrong = hashlib.sha256(b"different").hexdigest()
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        "\n".join(
            (
                "[[prompts]]",
                'prompt_id = "market-context"',
                'prompt_version = "1.0.0"',
                'role = "MARKET_CONTEXT"',
                'file = "prompt.md"',
                f'content_digest = "sha256:{wrong}"',
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromptRegistryError, match="digest"):
        PromptRegistry(manifest)


def test_registry_rejects_unregistered_reference_without_fallback() -> None:
    with pytest.raises(PromptRegistryError, match="not registered"):
        prompt_registry().get("unknown-prompt", "1.0.0")
