"""Explicitly isolated MetaTrader 5 DEMO execution implementation."""

from ai_trading_team.execution.mt5_demo.adapter import MT5DemoExecutionAdapter
from ai_trading_team.execution.mt5_demo.backend import MetaTrader5DemoBackend

__all__ = ["MT5DemoExecutionAdapter", "MetaTrader5DemoBackend"]
