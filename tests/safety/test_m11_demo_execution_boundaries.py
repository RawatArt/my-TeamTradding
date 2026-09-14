"""Non-negotiable M11 DEMO execution safety boundaries."""

from pathlib import Path

import pytest

from ai_trading_team.config import (
    AppSettings,
    DemoExecutionSettings,
    QualificationSettings,
)
from ai_trading_team.config.startup import StartupPolicyError, validate_m11_startup
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.enums import ApplicationMode
from ai_trading_team.schemas.execution import DemoOrderIntent


def test_m11_defaults_to_non_executing_shadow_and_prohibits_live() -> None:
    settings = AppSettings()

    assert settings.app_mode is ApplicationMode.SHADOW
    assert not settings.demo_execution.enabled
    validate_m11_startup(settings)
    with pytest.raises(StartupPolicyError):
        validate_m11_startup(AppSettings(app_mode=ApplicationMode.LIVE))


@pytest.mark.parametrize("field", ["enable_live_trading", "live_trading_acknowledged"])
def test_m11_rejects_every_live_enablement_flag(field: str) -> None:
    with pytest.raises(StartupPolicyError):
        validate_m11_startup(AppSettings.model_validate({field: True}))


def test_demo_execution_requires_demo_mode_and_exclusive_task_selection() -> None:
    enabled = DemoExecutionSettings(enabled=True)
    with pytest.raises(StartupPolicyError, match="explicit DEMO"):
        validate_m11_startup(AppSettings(demo_execution=enabled))
    with pytest.raises(StartupPolicyError, match="separate tasks"):
        validate_m11_startup(
            AppSettings(
                app_mode=ApplicationMode.DEMO,
                demo_execution=enabled,
                qualification=QualificationSettings(enabled=True),
            )
        )


def test_order_send_exists_only_at_the_narrow_demo_backend_mutation_point() -> None:
    root = Path("src/ai_trading_team")
    occurrences: list[Path] = []
    for path in root.rglob("*.py"):
        if "order_send" in path.read_text(encoding="utf-8"):
            occurrences.append(path.relative_to(root))

    assert occurrences == [Path("execution/mt5_demo/backend.py")]


def test_no_forbidden_mt5_or_position_mutation_surface_was_added() -> None:
    root = Path("src/ai_trading_team/execution")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = (
        "symbol_select",
        "TRADE_ACTION_PENDING",
        "TRADE_ACTION_SLTP",
        "position_close",
        "position_modify",
        "order_modify",
        "order_cancel",
    )
    assert all(token not in source for token in forbidden)
    assert not hasattr(MT5ReadOnlyClient, "order_send")
    assert not hasattr(MT5ReadOnlyClient, "symbol_select")


def test_agents_cannot_import_execution_and_execution_cannot_invoke_agents() -> None:
    agents = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/ai_trading_team/agents").rglob("*.py")
    )
    execution = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/ai_trading_team/execution").rglob("*.py")
    )

    assert "ai_trading_team.execution" not in agents
    assert "RuntimeRouter" not in execution
    assert "BaseAgent" not in execution
    assert "MetaTrader5" not in Path(
        "src/ai_trading_team/execution/service.py"
    ).read_text(encoding="utf-8")


def test_confidence_is_absent_from_execution_and_risk_input_contracts() -> None:
    assert "confidence" not in DemoOrderIntent.model_fields
    assert "confidence" not in RiskEngine.evaluate.__annotations__
