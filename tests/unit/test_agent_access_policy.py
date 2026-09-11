from types import MappingProxyType

import pytest
from pydantic import ValidationError
from tests.fakes.agents import market_view

from ai_trading_team.agents.access import ROLE_INFORMATION_ACCESS, can_access
from ai_trading_team.schemas.enums import AgentRole, InformationResource
from ai_trading_team.schemas.orchestration import MarketContextInput, PerformanceReviewInput


def test_access_matrix_covers_every_role_and_is_immutable() -> None:
    assert isinstance(ROLE_INFORMATION_ACCESS, MappingProxyType)
    assert set(ROLE_INFORMATION_ACCESS) == set(AgentRole)


def test_parallel_stage_roles_cannot_see_upstream_or_sensitive_resources() -> None:
    for role in (
        AgentRole.MARKET_CONTEXT,
        AgentRole.TREND_ANALYST,
        AgentRole.PRICE_ACTION_ANALYST,
    ):
        assert can_access(role, InformationResource.MARKET_SNAPSHOT_VIEW)
        assert not can_access(role, InformationResource.UPSTREAM_AGENT_OUTPUTS)
        assert not can_access(role, InformationResource.TRADE_PROPOSAL)
        assert not can_access(role, InformationResource.RISK_DECISION)
        assert not can_access(role, InformationResource.PERFORMANCE_HISTORY)


def test_only_performance_reviewer_can_see_risk_decisions() -> None:
    permitted = {
        role for role in AgentRole if can_access(role, InformationResource.RISK_DECISION)
    }

    assert permitted == {AgentRole.PERFORMANCE_REVIEWER}


def test_performance_reviewer_has_no_current_market_view_field() -> None:
    assert "market" not in PerformanceReviewInput.model_fields


def test_role_input_rejects_fields_outside_its_contract() -> None:
    view = market_view()

    with pytest.raises(ValidationError):
        MarketContextInput.model_validate(
            {
                "cycle_id": view.cycle_id,
                "snapshot_id": view.snapshot_id,
                "market": view,
                "risk_decision": {},
            }
        )
