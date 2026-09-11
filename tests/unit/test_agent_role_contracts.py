import inspect

import pytest
from tests.fakes.agents import descriptor, trend_output

from ai_trading_team.agents import BaseAgent
from ai_trading_team.agents.roles import (
    ChiefTraderAgent,
    EntryAnalyst,
    MarketContextAgent,
    PerformanceReviewer,
    PriceActionAnalyst,
    QuantResearcher,
    SeniorQuantDeveloper,
    SkepticAgent,
    TrendAnalyst,
)
from ai_trading_team.schemas.agents import TrendAnalysisOutput
from ai_trading_team.schemas.enums import AgentExecutionProfile, AgentRole
from ai_trading_team.schemas.orchestration import TrendAnalysisInput

ROLE_CONTRACTS = (
    MarketContextAgent,
    TrendAnalyst,
    PriceActionAnalyst,
    EntryAnalyst,
    QuantResearcher,
    SeniorQuantDeveloper,
    SkepticAgent,
    ChiefTraderAgent,
    PerformanceReviewer,
)


class FakeTrendAnalyst(TrendAnalyst):
    async def analyze(self, context: TrendAnalysisInput) -> TrendAnalysisOutput:
        return trend_output()


def test_all_nine_roles_extend_shared_abstract_base() -> None:
    assert len(ROLE_CONTRACTS) == 9
    assert all(issubclass(role, BaseAgent) for role in ROLE_CONTRACTS)
    assert all(inspect.isabstract(role) for role in ROLE_CONTRACTS)


def test_descriptor_role_must_match_concrete_role_contract() -> None:
    with pytest.raises(ValueError, match="does not match"):
        FakeTrendAnalyst(descriptor(AgentRole.SKEPTIC))


def test_realtime_role_accepts_its_allowed_profile() -> None:
    agent = FakeTrendAnalyst(descriptor(AgentRole.TREND_ANALYST))

    assert agent.descriptor.execution_profile is AgentExecutionProfile.REALTIME


@pytest.mark.parametrize(
    "role",
    [AgentRole.QUANT_RESEARCHER, AgentRole.SENIOR_QUANT_DEVELOPER],
)
def test_quant_roles_are_conditional_or_offline_but_not_realtime(role: AgentRole) -> None:
    from ai_trading_team.agents.access import execution_profile_allowed

    assert execution_profile_allowed(role, AgentExecutionProfile.CONDITIONAL)
    assert execution_profile_allowed(role, AgentExecutionProfile.OFFLINE)
    assert not execution_profile_allowed(role, AgentExecutionProfile.REALTIME)


def test_performance_reviewer_is_offline_only() -> None:
    from ai_trading_team.agents.access import execution_profile_allowed

    assert execution_profile_allowed(
        AgentRole.PERFORMANCE_REVIEWER, AgentExecutionProfile.OFFLINE
    )
    assert not execution_profile_allowed(
        AgentRole.PERFORMANCE_REVIEWER, AgentExecutionProfile.REALTIME
    )
