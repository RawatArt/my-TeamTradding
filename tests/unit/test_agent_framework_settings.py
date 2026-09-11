import pytest
from pydantic import ValidationError

from ai_trading_team.config import AgentFrameworkSettings, AppSettings


def test_agent_framework_defaults_to_one_bounded_debate_round() -> None:
    settings = AgentFrameworkSettings()

    assert settings.max_debate_rounds == 1


@pytest.mark.parametrize("value", [-1, 4])
def test_agent_framework_rejects_unbounded_debate_configuration(value: int) -> None:
    with pytest.raises(ValidationError):
        AgentFrameworkSettings(max_debate_rounds=value)


def test_nested_agent_settings_load_without_model_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTS__MAX_DEBATE_ROUNDS", "2")

    settings = AppSettings()

    assert settings.agents.max_debate_rounds == 2
