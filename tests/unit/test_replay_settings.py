"""M8 configuration boundary tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_trading_team.config import ReplaySettings


def test_replay_settings_are_inert_by_default() -> None:
    settings = ReplaySettings()
    assert settings.enabled is False
    assert settings.repository_path == Path("data/replay.sqlite3")


def test_replay_settings_are_immutable_and_strict() -> None:
    settings = ReplaySettings()
    with pytest.raises(ValidationError):
        settings.enabled = True
    with pytest.raises(ValidationError):
        ReplaySettings(unknown=True)  # type: ignore[call-arg]
