"""M11 DEMO execution configuration remains inert by default."""

from pathlib import Path

import pytest

from ai_trading_team.config import AppSettings, DemoExecutionSettings


def test_demo_execution_settings_are_disabled_and_local_by_default() -> None:
    settings = DemoExecutionSettings()

    assert not settings.enabled
    assert settings.repository_path == Path("data/demo_execution.sqlite3")
    assert settings.policy_path == Path("config/demo_execution_policy.toml")
    assert settings.environment_acceptance_path == Path(
        "config/demo_environment_acceptance.toml"
    )
    assert settings.approval_path == Path("config/demo_execution_approval.toml")


def test_demo_execution_settings_load_from_nested_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_EXECUTION__ENABLED", "true")
    monkeypatch.setenv("DEMO_EXECUTION__REPOSITORY_PATH", "data/custom-demo.db")

    settings = AppSettings()

    assert settings.demo_execution.enabled
    assert settings.demo_execution.repository_path == Path("data/custom-demo.db")
