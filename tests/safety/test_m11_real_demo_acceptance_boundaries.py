"""Safety boundaries specific to the real-DEMO acceptance addendum."""

from pathlib import Path

from ai_trading_team.config import AppSettings
from ai_trading_team.config.startup import StartupPolicyError, validate_m11_startup
from ai_trading_team.schemas.enums import ApplicationMode


def test_default_tests_have_no_real_demo_mutation_enablement() -> None:
    source = Path("scripts/m11_real_demo_acceptance.py").read_text(encoding="utf-8")
    assert "RUN_M11_REAL_DEMO_EXECUTION" in source
    assert "settings.app_mode is not ApplicationMode.DEMO" in source
    assert "not settings.demo_execution.enabled" in source
    assert "--execute-once" in source
    assert "order_send" not in source
    assert source.index("_require_explicit_mutation_gate(settings)") < source.index(
        'import_module("MetaTrader5")'
    )


def test_real_demo_addendum_has_no_close_modify_pending_or_retry_surface() -> None:
    files = (
        Path("src/ai_trading_team/execution/real_demo_acceptance.py"),
        Path("src/ai_trading_team/execution/vendor_boundary.py"),
        Path("src/ai_trading_team/schemas/execution_acceptance.py"),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = (
        "symbol_select",
        "TRADE_ACTION_PENDING",
        "TRADE_ACTION_SLTP",
        "position_close",
        "position_modify",
        "partial_close",
        "trailing_stop",
    )
    assert all(token not in source for token in forbidden)


def test_live_remains_prohibited() -> None:
    try:
        validate_m11_startup(AppSettings(app_mode=ApplicationMode.LIVE))
    except StartupPolicyError:
        pass
    else:
        raise AssertionError("LIVE must remain prohibited")
