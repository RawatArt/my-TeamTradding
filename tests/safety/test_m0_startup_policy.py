import pytest

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M0_STARTUP_POLICY, StartupPolicy, StartupPolicyError
from ai_trading_team.schemas.enums import ApplicationMode


def test_m0_policy_rejects_live_while_core_configuration_accepts_it() -> None:
    settings = AppSettings(app_mode=ApplicationMode.LIVE)

    assert settings.app_mode is ApplicationMode.LIVE
    with pytest.raises(StartupPolicyError, match="LIVE mode is prohibited"):
        M0_STARTUP_POLICY.validate(settings)


@pytest.mark.parametrize(
    ("enable_live_trading", "live_trading_acknowledged"),
    [(True, False), (False, True)],
)
def test_m0_policy_rejects_every_live_trading_flag(
    enable_live_trading: bool, live_trading_acknowledged: bool
) -> None:
    settings = AppSettings(
        enable_live_trading=enable_live_trading,
        live_trading_acknowledged=live_trading_acknowledged,
    )

    with pytest.raises(StartupPolicyError, match="live-trading flags are prohibited"):
        M0_STARTUP_POLICY.validate(settings)


@pytest.mark.parametrize(
    "mode",
    [ApplicationMode.BACKTEST, ApplicationMode.SHADOW, ApplicationMode.DEMO],
)
def test_m0_policy_accepts_non_live_modes_with_live_flags_disabled(mode: ApplicationMode) -> None:
    settings = AppSettings(app_mode=mode)

    M0_STARTUP_POLICY.validate(settings)


def test_future_policy_can_be_replaced_without_changing_core_settings_model() -> None:
    future_policy = StartupPolicy(
        milestone="FUTURE_REVIEWED_MILESTONE",
        allowed_modes=frozenset({ApplicationMode.LIVE}),
        allow_live_trading=True,
    )
    settings = AppSettings(
        app_mode=ApplicationMode.LIVE,
        enable_live_trading=True,
        live_trading_acknowledged=True,
    )

    future_policy.validate(settings)
