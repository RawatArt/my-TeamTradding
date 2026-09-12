"""Narrow capabilities used by the M9 coordinator."""

from datetime import datetime
from typing import Protocol

from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.common import CycleId, SnapshotId, Symbol
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.features import MarketFeatureSet
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5AccountInfo, MT5Candle, MT5OpenPosition
from ai_trading_team.schemas.observation import RiskContextEvidence
from ai_trading_team.schemas.risk import AccountRiskContext
from ai_trading_team.schemas.shadow import ShadowDecisionRecord


class CompletedCandleSource(Protocol):
    def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int,
        include_incomplete: bool = False,
    ) -> tuple[MT5Candle, ...]: ...


class AccountContextSource(Protocol):
    def get_account_info(self) -> MT5AccountInfo: ...

    def get_positions(self, symbol: Symbol | None = None) -> tuple[MT5OpenPosition, ...]: ...


class SnapshotService(Protocol):
    def build_snapshot(
        self,
        cycle_id: CycleId,
        snapshot_id: SnapshotId,
        primary_timeframe: Timeframe,
    ) -> MarketSnapshot: ...


class FeatureService(Protocol):
    def calculate(self, snapshot: MarketSnapshot) -> MarketFeatureSet: ...


class ShadowCycleService(Protocol):
    async def run_shadow_cycle(
        self,
        snapshot: MarketSnapshot,
        account_risk_context: AccountRiskContext,
        *,
        market_view: AgentMarketView | None = None,
    ) -> ShadowDecisionRecord: ...


class RiskContextService(Protocol):
    def build(self, snapshot: MarketSnapshot) -> RiskContextEvidence: ...


class ProviderEligibilityService(Protocol):
    def require_eligible(self, market_view: AgentMarketView, *, at: datetime) -> None: ...
