import pytest

from ai_trading_team.config import M6_STARTUP_POLICY, AppSettings, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m6_accepts_shadow_mode() -> None:
    M6_STARTUP_POLICY.validate(AppSettings(app_mode=ApplicationMode.SHADOW))


@pytest.mark.parametrize(
    "mode",
    [ApplicationMode.BACKTEST, ApplicationMode.DEMO, ApplicationMode.LIVE],
)
def test_m6_rejects_every_non_shadow_mode(mode: ApplicationMode) -> None:
    with pytest.raises(StartupPolicyError):
        M6_STARTUP_POLICY.validate(AppSettings(app_mode=mode))


def test_m6_rejects_live_enablement_flags_even_in_shadow() -> None:
    with pytest.raises(StartupPolicyError):
        M6_STARTUP_POLICY.validate(
            AppSettings(app_mode=ApplicationMode.SHADOW, enable_live_trading=True)
        )
