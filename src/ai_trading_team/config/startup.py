"""Replaceable milestone-specific startup safety policies."""

from dataclasses import dataclass

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.schemas.enums import ApplicationMode


class StartupPolicyError(RuntimeError):
    """Raised when validated settings are unsafe for the active milestone."""


@dataclass(frozen=True, slots=True)
class StartupPolicy:
    """Defines modes and capabilities permitted for a specific milestone."""

    milestone: str
    allowed_modes: frozenset[ApplicationMode]
    allow_live_trading: bool

    def validate(self, settings: AppSettings) -> None:
        """Fail startup if settings exceed this milestone's allowed capabilities."""
        if settings.app_mode not in self.allowed_modes:
            raise StartupPolicyError(
                f"{settings.app_mode.value} mode is prohibited by the {self.milestone} policy"
            )
        if not self.allow_live_trading and (
            settings.enable_live_trading or settings.live_trading_acknowledged
        ):
            raise StartupPolicyError(
                f"live-trading flags are prohibited by the {self.milestone} policy"
            )


M0_STARTUP_POLICY = StartupPolicy(
    milestone="M0",
    allowed_modes=frozenset(
        {ApplicationMode.BACKTEST, ApplicationMode.SHADOW, ApplicationMode.DEMO}
    ),
    allow_live_trading=False,
)

M1_STARTUP_POLICY = StartupPolicy(
    milestone="M1",
    allowed_modes=M0_STARTUP_POLICY.allowed_modes,
    allow_live_trading=False,
)
