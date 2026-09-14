"""Composition of existing M1/M2/M3 read-only inputs for M11 preflight."""

from collections.abc import Callable
from datetime import datetime

from ai_trading_team.execution.identifiers import environment_fingerprint
from ai_trading_team.execution.protocols import DemoExecutionAdapter
from ai_trading_team.market.service import MarketDataService
from ai_trading_team.mt5.client import MT5ReadOnlyClient
from ai_trading_team.observation.risk_context import AccountRiskContextProvider
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.execution import FreshExecutionObservation
from ai_trading_team.utils.time import utc_now


class M11ExecutionObservationSource:
    """Use only accepted read-only services to build a fresh execution observation."""

    def __init__(
        self,
        market_data: MarketDataService,
        account_context: AccountRiskContextProvider,
        mt5: MT5ReadOnlyClient,
        capabilities: DemoExecutionAdapter,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._market_data = market_data
        self._account_context = account_context
        self._mt5 = mt5
        self._capabilities = capabilities
        self._clock = clock

    def capture(self, cycle_id: str, execution_snapshot_id: str) -> FreshExecutionObservation:
        snapshot = self._market_data.build_snapshot(
            cycle_id,
            execution_snapshot_id,
            Timeframe.M15,
        )
        risk_context = self._account_context.build(snapshot)
        positions = self._mt5.get_positions(None)
        health = self._mt5.health_check()
        capabilities = self._capabilities.get_execution_capabilities(snapshot.symbol)
        return FreshExecutionObservation(
            captured_at=self._clock(),
            environment_ref=environment_fingerprint(snapshot.account, health),
            snapshot=snapshot,
            risk_context_evidence=risk_context,
            account_positions=positions,
            capabilities=capabilities,
        )
