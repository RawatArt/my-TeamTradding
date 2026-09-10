"""Finite domain states kept separate by responsibility."""

from enum import StrEnum


class ApplicationMode(StrEnum):
    """How the application is intended to operate."""

    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    DEMO = "DEMO"
    LIVE = "LIVE"


class RiskState(StrEnum):
    """Account-level risk posture, independent of application mode."""

    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    SAFE_MODE = "SAFE_MODE"
    HALTED = "HALTED"


class RiskDecisionStatus(StrEnum):
    """Outcome produced by a future deterministic Risk Engine."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HALTED = "HALTED"


class TradeAction(StrEnum):
    """Permitted high-level decision actions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSide(StrEnum):
    """Directional side for a proposal; HOLD is intentionally excluded."""

    BUY = "BUY"
    SELL = "SELL"


class Timeframe(StrEnum):
    """Initial configured analysis timeframes."""

    M15 = "M15"
    H1 = "H1"
    H4 = "H4"


class MarketRegime(StrEnum):
    """Finite market-context labels specified for future analysis."""

    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    UNCERTAIN = "UNCERTAIN"

