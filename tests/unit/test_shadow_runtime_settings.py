from pathlib import Path

from ai_trading_team.config import AppSettings, ShadowRuntimeSettings
from ai_trading_team.schemas.enums import QuantStageSelection


def test_shadow_runtime_defaults_are_inert_and_skip_quant() -> None:
    settings = ShadowRuntimeSettings()
    assert settings.enabled is False
    assert settings.quant_stage_selection is QuantStageSelection.SKIP
    assert settings.audit_database_path == Path("data/shadow_audit.sqlite3")


def test_shadow_runtime_environment_configuration_is_typed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SHADOW__ENABLED", "true")
    monkeypatch.setenv("SHADOW__QUANT_STAGE_SELECTION", "QUANT_RESEARCH_ONLY")
    settings = AppSettings()

    assert settings.shadow.enabled is True
    assert settings.shadow.quant_stage_selection is QuantStageSelection.QUANT_RESEARCH_ONLY
