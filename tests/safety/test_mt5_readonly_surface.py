import inspect
from pathlib import Path

import ai_trading_team.mt5 as public_mt5
from ai_trading_team.mt5.client import MT5ReadOnlyClient
from ai_trading_team.mt5.protocols import MT5ReadBackend

EXPECTED_PUBLIC_METHODS = {
    "get_account_info",
    "get_candles",
    "get_positions",
    "get_symbol_info",
    "get_symbols",
    "get_tick",
    "health_check",
    "initialize",
    "shutdown",
}
FORBIDDEN_IDENTIFIERS = {
    "order_send",
    "order_check",
    "orders_get",
    "position_close",
    "position_modify",
    "symbol_select",
}


def public_method_names(subject: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(subject, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_public_client_exposes_exactly_the_approved_readonly_surface() -> None:
    assert public_method_names(MT5ReadOnlyClient) == EXPECTED_PUBLIC_METHODS
    assert not hasattr(MT5ReadOnlyClient, "__getattr__")


def test_internal_backend_protocol_contains_no_terminal_or_trade_mutation_api() -> None:
    protocol_methods = public_method_names(MT5ReadBackend)

    assert protocol_methods.isdisjoint(FORBIDDEN_IDENTIFIERS)


def test_public_mt5_package_exports_no_backend_or_execution_capability() -> None:
    assert set(public_mt5.__all__) == {
        "MAX_CANDLE_COUNT",
        "MT5ClientError",
        "MT5ErrorCategory",
        "MT5ReadOnlyClient",
    }


def test_production_mt5_source_contains_no_forbidden_api_identifier() -> None:
    source_root = Path(__file__).parents[2] / "src" / "ai_trading_team" / "mt5"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))

    for identifier in FORBIDDEN_IDENTIFIERS:
        assert identifier not in source
