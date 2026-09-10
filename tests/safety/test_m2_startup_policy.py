import pytest

from ai_trading_team.config import M2_STARTUP_POLICY, AppSettings, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m2_startup_policy_rejects_live_mode() -> None:
    with pytest.raises(StartupPolicyError):
        M2_STARTUP_POLICY.validate(AppSettings(app_mode=ApplicationMode.LIVE))


def test_m2_startup_policy_rejects_live_enablement_flags() -> None:
    with pytest.raises(StartupPolicyError):
        M2_STARTUP_POLICY.validate(AppSettings(enable_live_trading=True))
