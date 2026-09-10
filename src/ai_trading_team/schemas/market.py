"""Minimal M0 market-data boundary contracts."""

from decimal import Decimal

from pydantic import model_validator

from ai_trading_team.schemas.common import NonNegativeDecimal, Symbol, TraceableRecord
from ai_trading_team.schemas.enums import Timeframe


class MarketQuote(TraceableRecord):
    """A validated bid/ask quote; full MarketSnapshot belongs to M2."""

    symbol: Symbol
    timeframe: Timeframe
    bid: NonNegativeDecimal
    ask: NonNegativeDecimal
    spread: NonNegativeDecimal

    @model_validator(mode="after")
    def validate_price_relationships(self) -> "MarketQuote":
        """Ensure ask and declared spread agree exactly in decimal arithmetic."""
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        expected_spread = self.ask - self.bid
        if self.spread != expected_spread:
            raise ValueError("spread must equal ask minus bid")
        return self

    @property
    def mid(self) -> Decimal:
        """Return the exact decimal midpoint without binary float conversion."""
        return (self.bid + self.ask) / Decimal("2")

