"""Finite domain states kept separate by responsibility."""

from enum import IntEnum, StrEnum


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


class DataValidityState(StrEnum):
    """Structural validity, kept independent from freshness and tradeability."""

    VALID = "VALID"
    INVALID = "INVALID"


class FreshnessState(StrEnum):
    """Whether a structurally valid observation is within its configured age limit."""

    FRESH = "FRESH"
    STALE = "STALE"


class SnapshotWarningCode(StrEnum):
    """Non-fatal consistency and freshness findings attached to a valid snapshot."""

    STALE_TICK = "STALE_TICK"
    STALE_ACCOUNT = "STALE_ACCOUNT"
    STALE_CANDLE = "STALE_CANDLE"
    SLOW_SNAPSHOT = "SLOW_SNAPSHOT"
    OUT_OF_SCOPE_POSITION_OMITTED = "OUT_OF_SCOPE_POSITION_OMITTED"


class MarketRegime(StrEnum):
    """Finite market-context labels specified for future analysis."""

    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    UNCERTAIN = "UNCERTAIN"


class MT5ConnectionState(StrEnum):
    """Observed MT5 terminal connection state."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class BrokerAccountMode(IntEnum):
    """MetaTrader 5 broker account classification."""

    DEMO = 0
    CONTEST = 1
    REAL = 2


class SymbolTradeMode(IntEnum):
    """MetaTrader 5 symbol trading availability value."""

    DISABLED = 0
    LONG_ONLY = 1
    SHORT_ONLY = 2
    CLOSE_ONLY = 3
    FULL = 4


class BrokerPositionSide(IntEnum):
    """Direction reported for an existing broker position."""

    BUY = 0
    SELL = 1
