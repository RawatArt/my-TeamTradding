"""M4 abstract agent foundation; no model runtime is implemented."""

from ai_trading_team.agents.access import (
    ROLE_EXECUTION_PROFILES,
    ROLE_INFORMATION_ACCESS,
    can_access,
    execution_profile_allowed,
)
from ai_trading_team.agents.base import BaseAgent
from ai_trading_team.agents.protocols import AgentRuntimeAdapter
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

__all__ = [
    "AgentRuntimeAdapter",
    "BaseAgent",
    "ChiefTraderAgent",
    "EntryAnalyst",
    "MarketContextAgent",
    "PerformanceReviewer",
    "PriceActionAnalyst",
    "QuantResearcher",
    "ROLE_EXECUTION_PROFILES",
    "ROLE_INFORMATION_ACCESS",
    "SeniorQuantDeveloper",
    "SkepticAgent",
    "TrendAnalyst",
    "can_access",
    "execution_profile_allowed",
]
