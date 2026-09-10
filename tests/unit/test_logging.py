import io
import json
import logging
from decimal import Decimal
from pathlib import Path

from pydantic import SecretStr

from ai_trading_team.config.settings import AppSettings, MT5Settings
from ai_trading_team.utils.logging import configure_logging


def test_structured_logger_preserves_context_and_redacts_credentials() -> None:
    stream = io.StringIO()
    logger = configure_logging(stream=stream)

    logger.info(
        "test_event",
        extra={
            "cycle_id": "cycle-003",
            "symbol": "EURUSD",
            "risk_amount": Decimal("0.25"),
            "api_key": "must-not-appear",
            "details": {"mt5_password": "also-must-not-appear"},
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["cycle_id"] == "cycle-003"
    assert payload["risk_amount"] == "0.25"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["details"]["mt5_password"] == "[REDACTED]"
    assert "must-not-appear" not in stream.getvalue()


def test_configure_logging_does_not_duplicate_handlers() -> None:
    first = io.StringIO()
    second = io.StringIO()
    logger = configure_logging(stream=first)
    logger = configure_logging(stream=second)

    logger.log(logging.INFO, "single_event")

    assert first.getvalue() == ""
    assert second.getvalue().count("single_event") == 1


def test_structured_logger_redacts_sensitive_values_inside_settings_models() -> None:
    stream = io.StringIO()
    logger = configure_logging(stream=stream)
    settings = AppSettings(
        mt5=MT5Settings(
            terminal_path=Path("C:/Users/private/terminal64.exe"),
            login=12345678,
            password=SecretStr("demo-password"),
            server="Broker-Demo",
        )
    )

    logger.info("settings_test", extra={"settings": settings})

    output = stream.getvalue()
    assert "12345678" not in output
    assert "demo-password" not in output
    assert "Broker-Demo" not in output
    assert "C:/Users/private" not in output
