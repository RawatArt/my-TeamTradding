import inspect
from pathlib import Path

from ai_trading_team.market.errors import MarketDataErrorCategory
from ai_trading_team.market.protocols import MarketDataSource
from ai_trading_team.market.service import MarketDataService
from ai_trading_team.schemas.market import MarketSnapshot

EXPECTED_SOURCE_METHODS = {
    "get_account_info",
    "get_candles",
    "get_positions",
    "get_symbol_info",
    "get_tick",
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


def test_m2_source_protocol_is_read_only_and_narrow() -> None:
    assert public_method_names(MarketDataSource) == EXPECTED_SOURCE_METHODS


def test_market_data_service_exposes_only_snapshot_composition() -> None:
    assert public_method_names(MarketDataService) == {"build_snapshot"}


def test_snapshot_has_no_tradeability_or_execution_field() -> None:
    assert "tradeable" not in MarketSnapshot.model_fields
    assert "tradeability" not in MarketSnapshot.model_fields
    assert "order" not in MarketSnapshot.model_fields


def test_strict_stale_tick_error_category_remains_available_without_being_default_policy() -> None:
    assert MarketDataErrorCategory.STALE_TICK.value == "STALE_TICK"


def test_m2_production_source_contains_no_mutation_identifier() -> None:
    source_root = Path(__file__).parents[2] / "src" / "ai_trading_team" / "market"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))

    for identifier in FORBIDDEN_IDENTIFIERS:
        assert identifier not in source
