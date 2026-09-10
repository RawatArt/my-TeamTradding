"""Typed boundary models for read-only MetaTrader 5 observations."""

from datetime import UTC, datetime

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    FiniteDecimal,
    NonNegativeDecimal,
    Symbol,
    VersionedObservation,
)
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    BrokerPositionSide,
    MT5ConnectionState,
    SymbolTradeMode,
    Timeframe,
)


def _normalize_source_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("source timestamp must be timezone-aware")
    return value.astimezone(UTC)


class MT5TerminalHealth(VersionedObservation):
    """Sanitized terminal health information."""

    connection_state: MT5ConnectionState
    authenticated: bool
    package_version: str
    terminal_version: str | None = None
    terminal_build: NonNegativeInt | None = None
    terminal_name: str | None = None
    terminal_company: str | None = None
    trade_api_disabled: bool | None = None


class MT5AccountInfo(VersionedObservation):
    """Account and margin information copied from the terminal."""

    account_id: PositiveInt = Field(repr=False)
    trade_mode: BrokerAccountMode
    leverage: PositiveInt
    limit_orders: NonNegativeInt
    margin_stop_out_mode: NonNegativeInt
    trade_allowed: bool
    expert_trading_allowed: bool
    margin_mode: NonNegativeInt
    currency_digits: NonNegativeInt
    fifo_close: bool
    balance: FiniteDecimal
    credit: FiniteDecimal
    profit: FiniteDecimal
    equity: FiniteDecimal
    margin: FiniteDecimal
    margin_free: FiniteDecimal
    margin_level: FiniteDecimal
    margin_stop_out_call: FiniteDecimal
    margin_stop_out_stop: FiniteDecimal
    margin_initial: FiniteDecimal
    margin_maintenance: FiniteDecimal
    assets: FiniteDecimal
    liabilities: FiniteDecimal
    commission_blocked: FiniteDecimal
    currency: str
    server: str = Field(repr=False)
    company: str


class MT5SymbolSummary(VersionedObservation):
    """Controlled symbol-discovery result."""

    symbol: Symbol
    description: str
    path: str
    selected: bool
    visible: bool


class MT5SymbolInfo(MT5SymbolSummary):
    """Broker-provided symbol properties required by later deterministic modules."""

    digits: NonNegativeInt
    point: NonNegativeDecimal
    trade_tick_size: NonNegativeDecimal
    trade_tick_value: FiniteDecimal
    trade_contract_size: NonNegativeDecimal
    volume_min: NonNegativeDecimal
    volume_max: NonNegativeDecimal
    volume_step: NonNegativeDecimal
    trade_stops_level: NonNegativeInt
    trade_freeze_level: NonNegativeInt
    currency_base: str
    currency_profit: str
    trading_mode: SymbolTradeMode


class MT5Tick(VersionedObservation):
    """Latest broker tick represented without raw MT5 objects."""

    symbol: Symbol
    source_time: datetime
    bid: FiniteDecimal
    ask: FiniteDecimal
    spread: NonNegativeDecimal
    last: FiniteDecimal
    volume: NonNegativeDecimal
    flags: NonNegativeInt

    _normalize_time = field_validator("source_time")(_normalize_source_time)


class MT5Candle(VersionedObservation):
    """One OHLCV bar returned from the read-only terminal adapter."""

    symbol: Symbol
    timeframe: Timeframe
    open_time: datetime
    open: FiniteDecimal
    high: FiniteDecimal
    low: FiniteDecimal
    close: FiniteDecimal
    tick_volume: NonNegativeInt
    broker_spread_points: NonNegativeInt
    real_volume: NonNegativeInt

    _normalize_time = field_validator("open_time")(_normalize_source_time)

    @model_validator(mode="after")
    def validate_ohlc_relationships(self) -> "MT5Candle":
        """Reject impossible OHLC relationships from malformed vendor data."""
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("candle high/low must contain its open and close")
        if self.high < self.low:
            raise ValueError("candle high must be greater than or equal to low")
        return self


class MT5OpenPosition(VersionedObservation):
    """Existing broker position; this model has no modification behavior."""

    ticket: PositiveInt
    identifier: PositiveInt
    symbol: Symbol
    side: BrokerPositionSide
    volume: NonNegativeDecimal
    open_time: datetime
    update_time: datetime
    price_open: FiniteDecimal
    stop_loss: FiniteDecimal
    take_profit: FiniteDecimal
    price_current: FiniteDecimal
    swap: FiniteDecimal
    profit: FiniteDecimal
    magic: int
    reason: NonNegativeInt
    comment: str
    external_id: str

    _normalize_open_time = field_validator("open_time")(_normalize_source_time)
    _normalize_update_time = field_validator("update_time")(_normalize_source_time)
