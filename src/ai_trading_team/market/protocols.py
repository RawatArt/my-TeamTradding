"""Application-owned read protocol consumed by the M2 composition service."""

from typing import Protocol

from ai_trading_team.schemas.common import Symbol
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5Candle,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5Tick,
)


class MarketDataSource(Protocol):
    """Narrow typed read surface structurally implemented by MT5ReadOnlyClient."""

    def get_account_info(self) -> MT5AccountInfo: ...

    def get_symbol_info(self, symbol: Symbol) -> MT5SymbolInfo: ...

    def get_tick(self, symbol: Symbol) -> MT5Tick: ...

    def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int,
        include_incomplete: bool = False,
    ) -> tuple[MT5Candle, ...]: ...

    def get_positions(self, symbol: Symbol | None = None) -> tuple[MT5OpenPosition, ...]: ...
