from pathlib import Path

from tests.fakes.runtime import contract_schema_has_no_status

from ai_trading_team.schemas.runtime import ModelGeneratedAgentBody

ROOT = Path(__file__).parents[2]
RUNTIME = ROOT / "src" / "ai_trading_team" / "runtime"
AGENTS = ROOT / "src" / "ai_trading_team" / "agents"


def source_text(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))


def test_model_body_has_no_trusted_status_or_runtime_control_fields() -> None:
    fields = ModelGeneratedAgentBody.model_fields

    assert "status" not in fields
    assert "risk_percent" not in fields
    assert "volume" not in fields
    assert "runtime_profile_ref" not in fields
    assert contract_schema_has_no_status()


def test_runtime_and_agent_packages_have_no_trading_system_dependencies() -> None:
    text = source_text(RUNTIME) + source_text(AGENTS)
    forbidden_imports = (
        "import MetaTrader5",
        "from ai_trading_team.mt5",
        "from ai_trading_team.risk",
        "from ai_trading_team.execution",
        "order_send",
        "symbol_select",
        "position_modify",
    )

    for forbidden in forbidden_imports:
        assert forbidden not in text


def test_provider_sdk_names_are_isolated_to_matching_adapter_packages() -> None:
    files = tuple(RUNTIME.rglob("*.py"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(RUNTIME).as_posix()
        if "from openai import" in text:
            assert relative.startswith("providers/openai/")
        if "from anthropic import" in text:
            assert relative.startswith("providers/anthropic/")
        if "from google import genai" in text:
            assert relative.startswith("providers/gemini/")


def test_runtime_has_no_multi_agent_scheduler_or_network_tool_access() -> None:
    text = source_text(RUNTIME)
    assert "REALTIME_DECISION_STAGES" not in text
    assert "MarketDataService" not in text
    assert "RiskEngine" not in text
    assert "requests." not in text
    assert "httpx." not in text
