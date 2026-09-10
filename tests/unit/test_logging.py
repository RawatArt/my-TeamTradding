import io
import json
import logging
from decimal import Decimal

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

