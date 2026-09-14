"""Typed application settings loaded from environment variables."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

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
from ai_trading_team.schemas.enums import ApplicationMode, QuantStageSelection

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


class MarketDataSettings(BaseModel):
    """Immutable M2 snapshot counts and descriptive freshness thresholds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    m15_candle_count: int = Field(default=200, ge=1, le=5_000)
    h1_candle_count: int = Field(default=200, ge=1, le=5_000)
    h4_candle_count: int = Field(default=200, ge=1, le=5_000)
    max_tick_age_seconds: int = Field(default=120, ge=1, le=86_400)
    max_account_age_seconds: int = Field(default=30, ge=1, le=86_400)
    max_m15_candle_age_seconds: int = Field(default=1_800, ge=1, le=604_800)
    max_h1_candle_age_seconds: int = Field(default=7_200, ge=1, le=604_800)
    max_h4_candle_age_seconds: int = Field(default=28_800, ge=1, le=604_800)
    slow_snapshot_seconds: int = Field(default=30, ge=1, le=3_600)


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


class AgentFrameworkSettings(BaseModel):
    """Inert M4 policy settings; these do not schedule or invoke an agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_debate_rounds: int = Field(default=1, ge=0, le=3)


class LLMRuntimeSettings(BaseModel):
    """M5 secrets and inert enablement; startup never invokes a provider automatically."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    budget_database_path: Path = Path("data/ai_budget.sqlite3")
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None


class ShadowRuntimeSettings(BaseModel):
    """M6 one-shot SHADOW orchestration settings; no scheduler is represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    audit_database_path: Path = Path("data/shadow_audit.sqlite3")
    provider_acceptance_path: Path = Path("config/provider_acceptance.toml")
    quant_stage_selection: QuantStageSelection = QuantStageSelection.SKIP


class FeatureEngineSettings(BaseModel):
    """Immutable M7 calculation choices included in feature provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configuration_version: Literal["1.0.0"] = "1.0.0"
    recent_range_lookback: int = Field(default=20, ge=1, le=5_000)
    swing_left_bars: int = Field(default=2, ge=1, le=100)
    swing_right_bars: int = Field(default=2, ge=1, le=100)

    @model_validator(mode="after")
    def validate_history_bounds(self) -> "FeatureEngineSettings":
        if self.swing_left_bars + self.swing_right_bars + 1 > 5_000:
            raise ValueError("configured swing window exceeds the M2 candle-count boundary")
        return self


class ReplaySettings(BaseModel):
    """Inert M8 offline replay settings; no scheduler or download is represented."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    repository_path: Path = Path("data/replay.sqlite3")


class ContinuousShadowSettings(BaseModel):
    """Bounded M9 polling policy; disabled unless explicitly enabled in SHADOW."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    discovery_lookback: int = Field(default=4, ge=1, le=100)
    maximum_decision_age_seconds: int = Field(default=180, ge=1, le=900)
    maximum_pending_cycles: Literal[1] = 1
    shutdown_grace_seconds: int = Field(default=30, ge=1, le=300)
    repository_path: Path = Path("data/continuous_shadow.sqlite3")
    symbol_acceptance_path: Path = Path("config/symbol_timestamp_acceptance.toml")
    provider_acceptance_path: Path = Path("config/continuous_shadow_acceptance.toml")


class QualificationSettings(BaseModel):
    """Inert M10 qualification configuration; it never enables a trading mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    repository_path: Path = Path("data/qualification.sqlite3")
    policy_path: Path = Path("config/shadow_graduation_policy.toml")
    run_path: Path = Path("config/qualification_run.toml")


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
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)
    risk: RiskConstitutionSettings = Field(default_factory=RiskConstitutionSettings)
    agents: AgentFrameworkSettings = Field(default_factory=AgentFrameworkSettings)
    llm: LLMRuntimeSettings = Field(default_factory=LLMRuntimeSettings)
    shadow: ShadowRuntimeSettings = Field(default_factory=ShadowRuntimeSettings)
    features: FeatureEngineSettings = Field(default_factory=FeatureEngineSettings)
    replay: ReplaySettings = Field(default_factory=ReplaySettings)
    continuous_shadow: ContinuousShadowSettings = Field(
        default_factory=ContinuousShadowSettings
    )
    qualification: QualificationSettings = Field(default_factory=QualificationSettings)
