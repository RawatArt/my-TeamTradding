"""Nine abstract role contracts with fixed input and output types."""

from ai_trading_team.agents.base import BaseAgent
from ai_trading_team.schemas.agents import (
    ChiefTraderOutput,
    EntryAnalysisOutput,
    MarketContextOutput,
    PerformanceReviewOutput,
    PriceActionOutput,
    QuantDeveloperOutput,
    QuantResearchOutput,
    SkepticOutput,
    TrendAnalysisOutput,
)
from ai_trading_team.schemas.enums import AgentRole
from ai_trading_team.schemas.orchestration import (
    ChiefTraderInput,
    EntryAnalysisInput,
    MarketContextInput,
    PerformanceReviewInput,
    PriceActionInput,
    QuantDeveloperInput,
    QuantResearchInput,
    SkepticInput,
    TrendAnalysisInput,
)


class MarketContextAgent(BaseAgent[MarketContextInput, MarketContextOutput]):
    role = AgentRole.MARKET_CONTEXT


class TrendAnalyst(BaseAgent[TrendAnalysisInput, TrendAnalysisOutput]):
    role = AgentRole.TREND_ANALYST


class PriceActionAnalyst(BaseAgent[PriceActionInput, PriceActionOutput]):
    role = AgentRole.PRICE_ACTION_ANALYST


class EntryAnalyst(BaseAgent[EntryAnalysisInput, EntryAnalysisOutput]):
    role = AgentRole.ENTRY_ANALYST


class QuantResearcher(BaseAgent[QuantResearchInput, QuantResearchOutput]):
    role = AgentRole.QUANT_RESEARCHER


class SeniorQuantDeveloper(BaseAgent[QuantDeveloperInput, QuantDeveloperOutput]):
    role = AgentRole.SENIOR_QUANT_DEVELOPER


class SkepticAgent(BaseAgent[SkepticInput, SkepticOutput]):
    role = AgentRole.SKEPTIC


class ChiefTraderAgent(BaseAgent[ChiefTraderInput, ChiefTraderOutput]):
    role = AgentRole.CHIEF_TRADER


class PerformanceReviewer(BaseAgent[PerformanceReviewInput, PerformanceReviewOutput]):
    role = AgentRole.PERFORMANCE_REVIEWER
