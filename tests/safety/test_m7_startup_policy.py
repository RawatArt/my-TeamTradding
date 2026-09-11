import pytest

from ai_trading_team.config import M7_STARTUP_POLICY, AppSettings, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m7_allows_only_shadow_mode() -> None:
    M7_STARTUP_POLICY.validate(AppSettings(app_mode=ApplicationMode.SHADOW))


@pytest.mark.parametrize(
    "mode",
    (ApplicationMode.BACKTEST, ApplicationMode.DEMO, ApplicationMode.LIVE),
)
def test_m7_rejects_non_shadow_modes(mode: ApplicationMode) -> None:
    with pytest.raises(StartupPolicyError):
        M7_STARTUP_POLICY.validate(AppSettings(app_mode=mode))


def test_m7_rejects_live_enablement_flags() -> None:
    with pytest.raises(StartupPolicyError):
        M7_STARTUP_POLICY.validate(AppSettings(enable_live_trading=True))

