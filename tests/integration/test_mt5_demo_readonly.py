"""Opt-in read-only acceptance test against a locally available MT5 demo terminal."""

import os
import sys

import pytest

from ai_trading_team.config.settings import AppSettings
from ai_trading_team.config.startup import M1_STARTUP_POLICY
from ai_trading_team.mt5 import MT5ReadOnlyClient
from ai_trading_team.schemas.enums import BrokerAccountMode, Timeframe

pytestmark = pytest.mark.mt5_integration

if os.getenv("RUN_MT5_INTEGRATION", "false").casefold() not in {"1", "true", "yes"}:
    pytest.skip("set RUN_MT5_INTEGRATION=true to enable MT5 demo reads", allow_module_level=True)

if sys.platform != "win32":
    pytest.skip("MetaTrader5 integration requires Windows", allow_module_level=True)


def test_demo_terminal_supports_all_m1_read_operations() -> None:
    settings = AppSettings()
    M1_STARTUP_POLICY.validate(settings)
    if settings.trading_symbol is None:
        pytest.fail("TRADING_SYMBOL is required for the opt-in MT5 integration test")

    client = MT5ReadOnlyClient(settings.mt5)
    try:
        health = client.initialize()
        assert health.authenticated is True
        account = client.get_account_info()
        if account.trade_mode is not BrokerAccountMode.DEMO:
            pytest.fail("the opt-in M1 integration test requires an MT5 demo account")

        symbols = client.get_symbols(settings.trading_symbol)
        assert any(item.symbol == settings.trading_symbol for item in symbols)
        symbol_info = client.get_symbol_info(settings.trading_symbol)
        assert symbol_info.selected is True
        client.get_tick(settings.trading_symbol)
        for timeframe in Timeframe:
            candles = client.get_candles(settings.trading_symbol, timeframe, 2)
            assert candles
        client.get_positions(settings.trading_symbol)
    finally:
        client.shutdown()
