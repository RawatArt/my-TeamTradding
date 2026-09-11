import inspect
from pathlib import Path

from ai_trading_team.agents.protocols import AgentRuntimeAdapter


def test_runtime_adapter_is_an_interface_without_implementation() -> None:
    assert getattr(AgentRuntimeAdapter, "_is_protocol", False)
    assert inspect.iscoroutinefunction(AgentRuntimeAdapter.invoke)
    assert AgentRuntimeAdapter.__subclasses__() == []


def test_runtime_protocol_has_no_vendor_or_network_dependency() -> None:
    source_path = (
        Path(__file__).parents[2]
        / "src"
        / "ai_trading_team"
        / "agents"
        / "protocols.py"
    )
    source = source_path.read_text(encoding="utf-8").casefold()

    for forbidden in ("openai", "anthropic", "gemini", "httpx", "requests", "socket"):
        assert forbidden not in source
