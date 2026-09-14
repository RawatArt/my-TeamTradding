"""M10 qualification configuration remains inert by default."""

from pathlib import Path

import pytest

from ai_trading_team.config import AppSettings, QualificationSettings


def test_qualification_settings_are_disabled_and_local_by_default() -> None:
    settings = QualificationSettings()

    assert not settings.enabled
    assert settings.repository_path == Path("data/qualification.sqlite3")
    assert settings.policy_path == Path("config/shadow_graduation_policy.toml")
    assert settings.run_path == Path("config/qualification_run.toml")


def test_qualification_settings_load_from_nested_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUALIFICATION__ENABLED", "true")
    monkeypatch.setenv("QUALIFICATION__REPOSITORY_PATH", "data/custom-qualification.db")

    settings = AppSettings()

    assert settings.qualification.enabled
    assert settings.qualification.repository_path == Path("data/custom-qualification.db")
