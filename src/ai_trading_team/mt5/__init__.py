"""Public read-only MetaTrader 5 integration surface."""

from ai_trading_team.mt5.client import MAX_CANDLE_COUNT, MT5ReadOnlyClient
from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory

__all__ = ["MAX_CANDLE_COUNT", "MT5ClientError", "MT5ErrorCategory", "MT5ReadOnlyClient"]
