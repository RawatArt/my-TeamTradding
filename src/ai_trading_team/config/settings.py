"""Typed application settings loaded from environment variables."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_trading_team.schemas.common import (
    Percentage,
    PerTradeRiskPercentage,
    PositiveDecimal,
    Symbol,
)
from ai_trading_team.schemas.enums import ApplicationMode


class RiskConstitutionSettings(BaseModel):
    """Immutable risk-policy configuration; no risk-engine behavior lives here.

    Percentage fields use percentage points: Decimal("0.50") means 0.50%.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    starting_balance: PositiveDecimal = Decimal("50")
    minimum_risk_percent: PerTradeRiskPercentage = Decimal("0.25")
    normal_risk_percent: PerTradeRiskPercentage = Decimal("0.50")
    maximum_risk_percent: PerTradeRiskPercentage = Decimal("1.00")
    maximum_open_positions: PositiveInt = 1
    maximum_daily_loss_percent: Percentage = Decimal("3")
    drawdown_warning_percent: Percentage = Decimal("5")
    drawdown_safe_mode_percent: Percentage = Decimal("8")
    drawdown_stop_percent: Percentage = Decimal("15")
    minimum_risk_reward: PositiveDecimal = Decimal("1.50")
    stop_loss_required: bool = True
    martingale_enabled: bool = False
    averaging_down_enabled: bool = False
    revenge_trading_enabled: bool = False

    @model_validator(mode="after")
    def validate_constitution(self) -> "RiskConstitutionSettings":
        """Reject risk configurations that violate the immutable constitution."""
        if not (
            self.minimum_risk_percent
            <= self.normal_risk_percent
            <= self.maximum_risk_percent
        ):
            raise ValueError("risk percentages must satisfy minimum <= normal <= maximum")
        if not (
            self.drawdown_warning_percent
            < self.drawdown_safe_mode_percent
            < self.drawdown_stop_percent
        ):
            raise ValueError("drawdown thresholds must satisfy warning < safe mode < stop")
        if not self.stop_loss_required:
            raise ValueError("stop loss is mandatory")
        if self.martingale_enabled:
            raise ValueError("martingale is forbidden")
        if self.averaging_down_enabled:
            raise ValueError("averaging down is forbidden")
        if self.revenge_trading_enabled:
            raise ValueError("revenge trading is forbidden")
        return self


class AppSettings(BaseSettings):
    """Core configuration model, independent of milestone startup policy."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    app_mode: ApplicationMode = ApplicationMode.SHADOW
    enable_live_trading: bool = False
    live_trading_acknowledged: bool = False
    trading_symbol: Symbol | None = None
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_json: bool = True
    risk: RiskConstitutionSettings = Field(default_factory=RiskConstitutionSettings)
