"""M9 exact feature projection and digest tests."""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.features import feature_snapshot

from ai_trading_team.features import MarketFeatureEngine
from ai_trading_team.prompts import PromptRegistry
from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.enums import AgentRole, FeatureUnit


def test_feature_enriched_market_view_has_reproducible_exact_digest() -> None:
    snapshot = feature_snapshot()
    features = MarketFeatureEngine().calculate(snapshot)

    first = AgentMarketView.from_snapshot(snapshot, features)
    second = AgentMarketView.from_snapshot(snapshot, features)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.schema_version == "2.0.0"
    assert first.features is not None
    assert first.agent_feature_view_digest == first.features.content_digest
    assert first.features.timeframes.m15.trend.ema_20.unit is FeatureUnit.PRICE
    assert isinstance(first.features.timeframes.m15.trend.ema_20.value, Decimal)


def test_feature_view_digest_changes_if_exact_allowlisted_fact_changes() -> None:
    snapshot = feature_snapshot()
    features = MarketFeatureEngine().calculate(snapshot)
    view = AgentMarketView.from_snapshot(snapshot, features)
    assert view.features is not None
    changed_features = view.features.model_copy(
        update={"source_configuration_digest": "sha256:" + "f" * 64}
    )

    assert changed_features.content_digest != view.features.content_digest
    with pytest.raises(ValidationError, match="digest"):
        AgentMarketView.model_validate(
            view.model_copy(update={"features": changed_features}).model_dump()
        )


def test_all_nine_roles_have_explicit_feature_aware_v2_prompts() -> None:
    registry = PromptRegistry.default()

    for role in AgentRole:
        prompt_id = {
            AgentRole.MARKET_CONTEXT: "market-context",
            AgentRole.TREND_ANALYST: "trend-analyst",
            AgentRole.PRICE_ACTION_ANALYST: "price-action",
            AgentRole.ENTRY_ANALYST: "entry-analyst",
            AgentRole.QUANT_RESEARCHER: "quant-researcher",
            AgentRole.SENIOR_QUANT_DEVELOPER: "senior-quant-developer",
            AgentRole.SKEPTIC: "skeptic",
            AgentRole.CHIEF_TRADER: "chief-trader",
            AgentRole.PERFORMANCE_REVIEWER: "performance-reviewer",
        }[role]
        artifact = registry.get(prompt_id, "2.0.0")
        assert artifact.role is role
        assert artifact.content_digest.startswith("sha256:")
