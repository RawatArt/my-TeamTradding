"""Orchestrator-owned invocation interfaces without a scheduling implementation."""

from datetime import datetime
from typing import Protocol, TypeVar

from ai_trading_team.agents.base import BaseAgent
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision

InputT = TypeVar("InputT", bound=CoreModel)
OutputT = TypeVar("OutputT", bound=CoreModel)


class AgentOrchestrator(Protocol):
    """Only this boundary may invoke an agent in a future runtime."""

    async def invoke_agent(
        self,
        agent: BaseAgent[InputT, OutputT],
        context: InputT,
    ) -> OutputT:
        ...


class DeterministicRiskStage(Protocol):
    """Structural interface for existing M3 risk evaluation after Chief Trader."""

    def evaluate(
        self,
        proposal: TradeProposal,
        snapshot: MarketSnapshot,
        account_context: AccountRiskContext,
        evaluated_at: datetime,
    ) -> RiskDecision:
        ...
