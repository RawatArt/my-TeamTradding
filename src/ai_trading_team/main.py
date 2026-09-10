"""M0-only application entry point.

This module validates configuration and reports startup. It contains no trading loop.
"""

from pydantic import ValidationError

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M0_STARTUP_POLICY, StartupPolicyError
from ai_trading_team.utils.logging import configure_logging, get_logger


def main() -> int:
    """Validate the M0 configuration and exit without performing trading work."""
    try:
        settings = AppSettings()
        M0_STARTUP_POLICY.validate(settings)
    except (ValidationError, StartupPolicyError) as exc:
        logger = configure_logging()
        logger.error("startup_rejected", extra={"error_type": type(exc).__name__})
        return 2

    logger = configure_logging(level=settings.log_level, json_output=settings.log_json)
    logger.info(
        "m0_startup_validated",
        extra={"app_mode": settings.app_mode.value, "milestone": "M0"},
    )
    get_logger(__name__).info("no_trading_components_are_active")
    return 0

