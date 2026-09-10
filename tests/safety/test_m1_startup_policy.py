import pytest

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M1_STARTUP_POLICY, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m1_policy_rejects_live_mode() -> None:
    settings = AppSettings(app_mode=ApplicationMode.LIVE)

    with pytest.raises(StartupPolicyError, match="LIVE mode is prohibited"):
        M1_STARTUP_POLICY.validate(settings)


def test_m1_policy_rejects_live_enablement_flags() -> None:
    settings = AppSettings(enable_live_trading=True)

    with pytest.raises(StartupPolicyError, match="live-trading flags are prohibited"):
        M1_STARTUP_POLICY.validate(settings)
