"""M6 application entry point.

This module validates configuration and reports startup. It does not automatically connect to
MT5 and contains no trading loop.
"""

from pydantic import ValidationError

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M6_STARTUP_POLICY, StartupPolicyError
from ai_trading_team.utils.logging import configure_logging, get_logger


def main() -> int:
    """Validate M6 configuration and exit without scheduling or trading activity."""
    try:
        settings = AppSettings()
        M6_STARTUP_POLICY.validate(settings)
    except (ValidationError, StartupPolicyError) as exc:
        logger = configure_logging()
        logger.error("startup_rejected", extra={"error_type": type(exc).__name__})
        return 2

    logger = configure_logging(level=settings.log_level, json_output=settings.log_json)
    logger.info(
        "m6_startup_validated",
        extra={"app_mode": settings.app_mode.value, "milestone": "M6"},
    )
    get_logger(__name__).info("no_trading_components_are_active")
    return 0
