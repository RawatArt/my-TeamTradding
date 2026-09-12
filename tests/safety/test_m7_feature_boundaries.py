import inspect
import json
from decimal import localcontext
from pathlib import Path

from tests.fakes.features import feature_snapshot

from ai_trading_team.features import MarketFeatureEngine, canonical_feature_json
from ai_trading_team.schemas.features import MarketFeatureSet


def test_feature_output_is_independent_of_process_decimal_context() -> None:
    snapshot = feature_snapshot()
    baseline = canonical_feature_json(MarketFeatureEngine().calculate(snapshot))

    with localcontext() as context:
        context.prec = 7
        changed_context = canonical_feature_json(MarketFeatureEngine().calculate(snapshot))

    assert changed_context == baseline


def test_decimal_values_are_json_strings_and_restore_as_decimal() -> None:
    result = MarketFeatureEngine().calculate(feature_snapshot())
    encoded = canonical_feature_json(result)
    payload = json.loads(encoded)

    assert isinstance(payload["timeframes"]["m15"]["trend"]["ema_20"]["value"], str)
    restored = MarketFeatureSet.model_validate_json(encoded)
    assert restored == result


def test_feature_contract_contains_no_strategy_or_execution_fields() -> None:
    schema = json.dumps(MarketFeatureSet.model_json_schema()).casefold()
    forbidden = (
        '"buy"',
        '"sell"',
        '"signal"',
        '"trade_score"',
        '"entry_score"',
        '"position_size"',
        '"order"',
    )

    assert all(item not in schema for item in forbidden)


def test_feature_package_has_no_runtime_broker_risk_or_execution_dependency() -> None:
    import ai_trading_team.features as package

    root = Path(inspect.getfile(package)).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = (
        "MetaTrader5",
        "ai_trading_team.mt5",
        "ai_trading_team.runtime",
        "ai_trading_team.risk",
        "ai_trading_team.execution",
        "openai",
        "anthropic",
        "google.genai",
    )

    assert all(item not in source for item in forbidden)


def test_m9_feature_expansion_preserves_legacy_view_as_feature_free() -> None:
    from ai_trading_team.schemas.agents import AgentMarketView

    assert AgentMarketView.model_fields["features"].default is None
    assert AgentMarketView.model_fields["agent_feature_view_digest"].default is None
