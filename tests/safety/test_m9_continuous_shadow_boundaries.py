"""Non-negotiable M9 safety boundaries."""

from pathlib import Path

import pytest

from ai_trading_team.config import AppSettings, ContinuousShadowSettings
from ai_trading_team.config.startup import StartupPolicyError, validate_m9_startup
from ai_trading_team.observation.runtime import ContinuousShadowRuntime
from ai_trading_team.schemas.agents import AgentFeatureView
from ai_trading_team.schemas.enums import ApplicationMode


def test_m9_runtime_exposes_no_execution_or_mutation_capability() -> None:
    public = {name for name in dir(ContinuousShadowRuntime) if not name.startswith("_")}
    assert public == {"health", "poll_once", "shutdown", "start"}


def test_m9_source_has_no_broker_mutation_or_second_risk_feature_algorithm() -> None:
    root = Path("src/ai_trading_team/observation")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "order_send",
        "symbol_select",
        "position_close",
        "position_modify",
        "MetaTrader5",
        "ema_series",
        "rsi_series",
        "atr_series",
        "adx_series",
        "PositionSizer",
    )
    assert all(token not in source for token in forbidden)


def test_agent_feature_projection_cannot_express_strategy_or_execution() -> None:
    schema = str(AgentFeatureView.model_json_schema()).casefold()
    assert "buy_signal" not in schema
    assert "sell_signal" not in schema
    assert "entry_score" not in schema
    assert "order" not in schema
    assert "confidence" not in schema


@pytest.mark.parametrize("mode", [ApplicationMode.DEMO, ApplicationMode.LIVE])
def test_m9_startup_prohibits_demo_and_live(mode: ApplicationMode) -> None:
    with pytest.raises(StartupPolicyError):
        validate_m9_startup(AppSettings(app_mode=mode))


def test_continuous_runtime_requires_explicit_shadow_enablement() -> None:
    validate_m9_startup(
        AppSettings(
            app_mode=ApplicationMode.SHADOW,
            continuous_shadow=ContinuousShadowSettings(enabled=True),
        )
    )
    with pytest.raises(StartupPolicyError, match="SHADOW"):
        validate_m9_startup(
            AppSettings(
                app_mode=ApplicationMode.BACKTEST,
                continuous_shadow=ContinuousShadowSettings(enabled=True),
            )
        )
