"""M8 remains offline and rejects DEMO/LIVE capability."""

import pytest

from ai_trading_team.config import (
    AppSettings,
    ReplaySettings,
    StartupPolicyError,
    validate_m8_startup,
)
from ai_trading_team.schemas.enums import ApplicationMode


def test_shadow_remains_inert_when_replay_is_disabled() -> None:
    validate_m8_startup(AppSettings(app_mode=ApplicationMode.SHADOW))


def test_explicit_backtest_mode_may_enable_offline_replay() -> None:
    validate_m8_startup(
        AppSettings(
            app_mode=ApplicationMode.BACKTEST, replay=ReplaySettings(enabled=True)
        )
    )


def test_shadow_cannot_enable_replay() -> None:
    with pytest.raises(StartupPolicyError):
        validate_m8_startup(
            AppSettings(
                app_mode=ApplicationMode.SHADOW, replay=ReplaySettings(enabled=True)
            )
        )


@pytest.mark.parametrize("mode", [ApplicationMode.DEMO, ApplicationMode.LIVE])
def test_demo_and_live_are_prohibited(mode: ApplicationMode) -> None:
    with pytest.raises(StartupPolicyError):
        validate_m8_startup(AppSettings(app_mode=mode))


def test_live_flags_remain_prohibited() -> None:
    with pytest.raises(StartupPolicyError):
        validate_m8_startup(
            AppSettings(
                app_mode=ApplicationMode.BACKTEST,
                enable_live_trading=True,
                live_trading_acknowledged=True,
            )
        )
