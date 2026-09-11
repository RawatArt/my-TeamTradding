"""Least-privilege construction of the accepted M4 role input contracts."""

from typing import TypedDict

from ai_trading_team.agents.access import can_access
from ai_trading_team.schemas.agents import (
    AgentMarketView,
    ChiefTraderOutput,
    EntryAnalysisOutput,
    QuantDeveloperOutput,
    QuantResearchOutput,
    SkepticOutput,
)
from ai_trading_team.schemas.enums import AgentRole, InformationResource
from ai_trading_team.schemas.orchestration import (
    ChiefTraderInput,
    EntryAnalysisInput,
    MarketContextInput,
    PriceActionInput,
    QuantDeveloperInput,
    QuantResearchInput,
    SkepticInput,
    StageOneContext,
    TrendAnalysisInput,
)


class _BaseInput(TypedDict):
    cycle_id: str
    snapshot_id: str
    market: AgentMarketView


class AgentInputFactory:
    """Build only explicitly authorized fields for each realtime role."""

    def __init__(self, market: AgentMarketView) -> None:
        self._market = market

    def market_context(self) -> MarketContextInput:
        self._require(AgentRole.MARKET_CONTEXT, InformationResource.MARKET_SNAPSHOT_VIEW)
        return MarketContextInput(**self._base())

    def trend(self) -> TrendAnalysisInput:
        self._require(AgentRole.TREND_ANALYST, InformationResource.MARKET_SNAPSHOT_VIEW)
        return TrendAnalysisInput(**self._base())

    def price_action(self) -> PriceActionInput:
        self._require(AgentRole.PRICE_ACTION_ANALYST, InformationResource.MARKET_SNAPSHOT_VIEW)
        return PriceActionInput(**self._base())

    def entry(self, stage_one: StageOneContext) -> EntryAnalysisInput:
        self._require(
            AgentRole.ENTRY_ANALYST,
            InformationResource.MARKET_SNAPSHOT_VIEW,
            InformationResource.UPSTREAM_AGENT_OUTPUTS,
        )
        return EntryAnalysisInput(**self._base(), stage_one=stage_one)

    def quant_research(
        self, stage_one: StageOneContext, entry: EntryAnalysisOutput
    ) -> QuantResearchInput:
        self._require(
            AgentRole.QUANT_RESEARCHER,
            InformationResource.MARKET_SNAPSHOT_VIEW,
            InformationResource.UPSTREAM_AGENT_OUTPUTS,
            InformationResource.QUANTITATIVE_EVIDENCE,
        )
        return QuantResearchInput(**self._base(), stage_one=stage_one, entry=entry)

    def quant_developer(
        self,
        stage_one: StageOneContext,
        entry: EntryAnalysisOutput,
        quant_research: QuantResearchOutput | None,
    ) -> QuantDeveloperInput:
        self._require(
            AgentRole.SENIOR_QUANT_DEVELOPER,
            InformationResource.MARKET_SNAPSHOT_VIEW,
            InformationResource.UPSTREAM_AGENT_OUTPUTS,
            InformationResource.QUANTITATIVE_EVIDENCE,
        )
        return QuantDeveloperInput(
            **self._base(),
            stage_one=stage_one,
            entry=entry,
            quant_research=quant_research,
        )

    def skeptic(
        self,
        stage_one: StageOneContext,
        entry: EntryAnalysisOutput,
        quant_research: QuantResearchOutput | None,
        quant_developer: QuantDeveloperOutput | None,
        chief_draft: ChiefTraderOutput | None,
    ) -> SkepticInput:
        self._require(
            AgentRole.SKEPTIC,
            InformationResource.MARKET_SNAPSHOT_VIEW,
            InformationResource.UPSTREAM_AGENT_OUTPUTS,
            InformationResource.TRADE_PROPOSAL,
            InformationResource.QUANTITATIVE_EVIDENCE,
        )
        return SkepticInput(
            **self._base(),
            stage_one=stage_one,
            entry=entry,
            quant_research=quant_research,
            quant_developer=quant_developer,
            chief_draft=chief_draft,
        )

    def chief(
        self,
        stage_one: StageOneContext,
        entry: EntryAnalysisOutput,
        quant_research: QuantResearchOutput | None,
        quant_developer: QuantDeveloperOutput | None,
        skeptic: SkepticOutput,
    ) -> ChiefTraderInput:
        self._require(
            AgentRole.CHIEF_TRADER,
            InformationResource.MARKET_SNAPSHOT_VIEW,
            InformationResource.UPSTREAM_AGENT_OUTPUTS,
            InformationResource.TRADE_PROPOSAL,
            InformationResource.QUANTITATIVE_EVIDENCE,
        )
        return ChiefTraderInput(
            **self._base(),
            stage_one=stage_one,
            entry=entry,
            quant_research=quant_research,
            quant_developer=quant_developer,
            skeptic=skeptic,
        )

    def _base(self) -> _BaseInput:
        return {
            "cycle_id": self._market.cycle_id,
            "snapshot_id": self._market.snapshot_id,
            "market": self._market,
        }

    @staticmethod
    def _require(role: AgentRole, *resources: InformationResource) -> None:
        if any(not can_access(role, resource) for resource in resources):
            raise PermissionError("role context exceeds the M4 information-access matrix")
