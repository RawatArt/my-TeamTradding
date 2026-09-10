"""Typed application settings loaded from environment variables."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    SecretStr,
    StringConstraints,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_trading_team.schemas.common import (
    Percentage,
    PerTradeRiskPercentage,
    PositiveDecimal,
    Symbol,
)
from ai_trading_team.schemas.enums import ApplicationMode

MT5Server = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class MT5Settings(BaseModel):
    """Read-only MT5 connection settings.

    Login and server are sensitive metadata for logging purposes. Password remains a SecretStr.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    terminal_path: Path | None = None
    login: PositiveInt | None = None
    password: SecretStr | None = None
    server: MT5Server | None = None
    timeout_ms: int = Field(default=60_000, ge=1_000, le=120_000)
    portable: bool = False

    @model_validator(mode="after")
    def require_complete_explicit_credentials(self) -> "MT5Settings":
        """Require login, password, and server together or omit all three."""
        supplied = (self.login is not None, self.password is not None, self.server is not None)
        if any(supplied) and not all(supplied):
            raise ValueError("MT5 login, password, and server must be configured together")
        if self.password is not None and not self.password.get_secret_value():
            raise ValueError("MT5 password must not be empty")
        return self

    @property
    def has_explicit_credentials(self) -> bool:
        """Return whether a complete explicit credential set is present."""
        return self.login is not None


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
    mt5: MT5Settings = Field(default_factory=MT5Settings)
    risk: RiskConstitutionSettings = Field(default_factory=RiskConstitutionSettings)
