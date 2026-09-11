import pytest

from ai_trading_team.config import M5_STARTUP_POLICY, AppSettings, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m5_defaults_to_shadow_with_runtime_disabled() -> None:
    settings = AppSettings.model_validate({})

    M5_STARTUP_POLICY.validate(settings)
    assert settings.app_mode is ApplicationMode.SHADOW
    assert settings.llm.enabled is False


def test_m5_rejects_live_mode_and_live_flags() -> None:
    with pytest.raises(StartupPolicyError):
        M5_STARTUP_POLICY.validate(AppSettings.model_validate({"app_mode": "LIVE"}))
    with pytest.raises(StartupPolicyError):
        M5_STARTUP_POLICY.validate(
            AppSettings.model_validate({"enable_live_trading": True})
        )
