import pytest

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M3_STARTUP_POLICY, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m3_defaults_to_shadow_and_prohibits_live_capability() -> None:
    settings = AppSettings.model_validate({})

    assert settings.app_mode is ApplicationMode.SHADOW
    M3_STARTUP_POLICY.validate(settings)
    assert not M3_STARTUP_POLICY.allow_live_trading


def test_m3_rejects_live_mode() -> None:
    with pytest.raises(StartupPolicyError):
        M3_STARTUP_POLICY.validate(AppSettings.model_validate({"app_mode": ApplicationMode.LIVE}))


@pytest.mark.parametrize("field", ["enable_live_trading", "live_trading_acknowledged"])
def test_m3_rejects_live_enablement_flags(field: str) -> None:
    with pytest.raises(StartupPolicyError):
        M3_STARTUP_POLICY.validate(AppSettings.model_validate({field: True}))
