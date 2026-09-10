import os
import sys
from uuid import uuid4

import pytest

from ai_trading_team.config import M2_STARTUP_POLICY, AppSettings
from ai_trading_team.market import MarketDataService
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.schemas.enums import BrokerAccountMode, DataValidityState, Timeframe

pytestmark = pytest.mark.mt5_integration

if os.getenv("RUN_MT5_INTEGRATION", "false").casefold() not in {"1", "true", "yes"}:
    pytest.skip("set RUN_MT5_INTEGRATION=true to enable MT5 demo reads", allow_module_level=True)

if sys.platform != "win32":
    pytest.skip("MetaTrader5 integration requires Windows", allow_module_level=True)


def test_demo_terminal_builds_one_complete_read_only_market_snapshot() -> None:
    settings = AppSettings()
    M2_STARTUP_POLICY.validate(settings)
    if settings.trading_symbol is None:
        pytest.fail("TRADING_SYMBOL is required for the opt-in M2 integration test")

    client = MT5ReadOnlyClient(settings.mt5)
    try:
        health = client.initialize()
        assert health.authenticated is True
        service = MarketDataService(client, settings.market_data, settings.trading_symbol)
        snapshot = service.build_snapshot(
            f"integration-cycle-{uuid4()}",
            f"integration-snapshot-{uuid4()}",
            Timeframe.M15,
        )
    finally:
        client.shutdown()

    assert snapshot.account.trade_mode is BrokerAccountMode.DEMO
    assert snapshot.consistency.validity is DataValidityState.VALID
    assert snapshot.symbol == settings.trading_symbol
    assert len(snapshot.candles.m15) == settings.market_data.m15_candle_count
    assert len(snapshot.candles.h1) == settings.market_data.h1_candle_count
    assert len(snapshot.candles.h4) == settings.market_data.h4_candle_count
    assert all(item.symbol == snapshot.symbol for item in snapshot.open_positions)
