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
    """Outcome produced by the deterministic Risk Engine."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HALTED = "HALTED"


class PositionSizingStatus(StrEnum):
    """Outcome of deterministic broker-volume sizing."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskReasonCode(StrEnum):
    """Stable machine-readable explanations for M3 risk decisions."""

    TRACEABILITY_MISMATCH = "TRACEABILITY_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    ACCOUNT_CONTEXT_MISMATCH = "ACCOUNT_CONTEXT_MISMATCH"
    ACCOUNT_CONTEXT_FUTURE_DATED = "ACCOUNT_CONTEXT_FUTURE_DATED"
    ACCOUNT_CONTEXT_PREDATES_SNAPSHOT = "ACCOUNT_CONTEXT_PREDATES_SNAPSHOT"
    TRADING_DAY_CONTEXT_INVALID = "TRADING_DAY_CONTEXT_INVALID"
    EVALUATION_TIMESTAMP_INVALID = "EVALUATION_TIMESTAMP_INVALID"
    ENTRY_PRICE_REQUIRED = "ENTRY_PRICE_REQUIRED"
    ENTRY_PRICE_INVALID = "ENTRY_PRICE_INVALID"
    STOP_LOSS_REQUIRED = "STOP_LOSS_REQUIRED"
    STOP_LOSS_INVALID = "STOP_LOSS_INVALID"
    TAKE_PROFIT_REQUIRED = "TAKE_PROFIT_REQUIRED"
    TAKE_PROFIT_INVALID = "TAKE_PROFIT_INVALID"
    INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
    INVALID_TAKE_PROFIT_GEOMETRY = "INVALID_TAKE_PROFIT_GEOMETRY"
    PRICE_NOT_ALIGNED_TO_TICK_SIZE = "PRICE_NOT_ALIGNED_TO_TICK_SIZE"
    STOP_DISTANCE_BELOW_BROKER_MINIMUM = "STOP_DISTANCE_BELOW_BROKER_MINIMUM"
    TAKE_PROFIT_DISTANCE_BELOW_BROKER_MINIMUM = (
        "TAKE_PROFIT_DISTANCE_BELOW_BROKER_MINIMUM"
    )
    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"
    SYMBOL_TRADING_DISABLED = "SYMBOL_TRADING_DISABLED"
    TRADE_SIDE_NOT_ALLOWED = "TRADE_SIDE_NOT_ALLOWED"
    ACCOUNT_TRADING_DISABLED = "ACCOUNT_TRADING_DISABLED"
    EXPERT_TRADING_DISABLED = "EXPERT_TRADING_DISABLED"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    ACCOUNT_POSITION_COUNT_INCONSISTENT = "ACCOUNT_POSITION_COUNT_INCONSISTENT"
    MAXIMUM_POSITIONS_REACHED = "MAXIMUM_POSITIONS_REACHED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    MAXIMUM_DRAWDOWN_REACHED = "MAXIMUM_DRAWDOWN_REACHED"
    INVALID_BROKER_RISK_METADATA = "INVALID_BROKER_RISK_METADATA"
    MINIMUM_VOLUME_EXCEEDS_RISK = "MINIMUM_VOLUME_EXCEEDS_RISK"
    POSITION_SIZE_INVARIANT_FAILED = "POSITION_SIZE_INVARIANT_FAILED"


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
