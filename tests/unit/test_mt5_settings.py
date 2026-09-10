from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from ai_trading_team.config.settings import AppSettings, MT5Settings


def test_mt5_settings_allow_current_terminal_session_without_credentials() -> None:
    settings = MT5Settings()

    assert settings.has_explicit_credentials is False
    assert settings.timeout_ms == 60_000
    assert settings.portable is False


def test_mt5_settings_accept_complete_explicit_credentials() -> None:
    settings = MT5Settings(
        terminal_path=Path("C:/Program Files/MetaTrader 5/terminal64.exe"),
        login=12345678,
        password=SecretStr("demo-password"),
        server="Broker-Demo",
    )

    assert settings.has_explicit_credentials is True
    assert isinstance(settings.password, SecretStr)
    assert settings.password.get_secret_value() == "demo-password"
    assert "demo-password" not in repr(settings)


@pytest.mark.parametrize(
    "payload",
    [
        {"login": 12345678},
        {"password": SecretStr("demo-password")},
        {"server": "Broker-Demo"},
        {"login": 12345678, "server": "Broker-Demo"},
    ],
)
def test_mt5_settings_reject_partial_credentials(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        MT5Settings.model_validate(payload)


def test_mt5_settings_reject_empty_password() -> None:
    with pytest.raises(ValidationError, match="password must not be empty"):
        MT5Settings(
            login=12345678,
            password=SecretStr(""),
            server="Broker-Demo",
        )


@pytest.mark.parametrize("timeout_ms", [999, 120_001])
def test_mt5_settings_reject_timeout_outside_bounds(timeout_ms: int) -> None:
    with pytest.raises(ValidationError):
        MT5Settings(timeout_ms=timeout_ms)


def test_app_settings_contain_a_separate_mt5_configuration_boundary() -> None:
    settings = AppSettings(mt5=MT5Settings())

    assert isinstance(settings.mt5, MT5Settings)
