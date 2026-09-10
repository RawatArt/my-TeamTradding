"""Conversion of vendor objects into application-owned Pydantic models."""

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import SupportsInt, cast

from pydantic import ValidationError

from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5Candle,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5SymbolSummary,
    MT5TerminalHealth,
    MT5Tick,
)

_MISSING = object()


def _mapping(raw: object, operation: str) -> Mapping[str, object]:
    if isinstance(raw, Mapping):
        return cast(Mapping[str, object], raw)

    asdict = getattr(raw, "_asdict", None)
    if callable(asdict):
        result = asdict()
        if isinstance(result, Mapping):
            return cast(Mapping[str, object], result)

    dtype = getattr(raw, "dtype", None)
    names = getattr(dtype, "names", None)
    getitem = getattr(raw, "__getitem__", None)
    if names is not None and callable(getitem):
        read_item = cast(Callable[[str], object], getitem)
        return {str(name): read_item(str(name)) for name in names}

    raise _mapping_error(operation, "vendor record is not a supported mapping")


def records(raw: object, operation: str) -> tuple[Mapping[str, object], ...]:
    """Convert a vendor record collection without exposing it to callers."""
    if isinstance(raw, (str, bytes, bytearray, Mapping)):
        raise _mapping_error(operation, "vendor collection has an invalid shape")
    if not isinstance(raw, Iterable):
        raise _mapping_error(operation, "vendor collection is not iterable")
    return tuple(_mapping(item, operation) for item in raw)


def _field(data: Mapping[str, object], name: str, operation: str) -> object:
    value = data.get(name, _MISSING)
    if value is _MISSING:
        raise _mapping_error(operation, f"vendor record is missing field {name}")
    return value


def _text(data: Mapping[str, object], name: str, operation: str) -> str:
    return str(_field(data, name, operation))


def _integer(data: Mapping[str, object], name: str, operation: str) -> int:
    value = _field(data, name, operation)
    if isinstance(value, bool):
        raise _mapping_error(operation, f"vendor field {name} is not an integer")
    int_method = getattr(value, "__int__", None)
    if not callable(int_method) and not isinstance(value, (str, bytes, bytearray)):
        raise _mapping_error(operation, f"vendor field {name} is not an integer")
    try:
        return int(cast(SupportsInt | str | bytes | bytearray, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _mapping_error(operation, f"vendor field {name} is not an integer") from exc


def _boolean(data: Mapping[str, object], name: str, operation: str) -> bool:
    value = _field(data, name, operation)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise _mapping_error(operation, f"vendor field {name} is not boolean")


def _decimal(data: Mapping[str, object], name: str, operation: str) -> Decimal:
    value = _field(data, name, operation)
    if isinstance(value, bool):
        raise _mapping_error(operation, f"vendor field {name} is not numeric")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise _mapping_error(operation, f"vendor field {name} is not numeric") from exc
    if not result.is_finite():
        raise _mapping_error(operation, f"vendor field {name} must be finite")
    return result


def _epoch_time(
    data: Mapping[str, object],
    operation: str,
    *,
    seconds_field: str,
    milliseconds_field: str | None = None,
) -> datetime:
    try:
        if milliseconds_field is not None and milliseconds_field in data:
            milliseconds = _integer(data, milliseconds_field, operation)
            seconds, remainder = divmod(milliseconds, 1_000)
            return datetime.fromtimestamp(seconds, UTC).replace(microsecond=remainder * 1_000)
        return datetime.fromtimestamp(_integer(data, seconds_field, operation), UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise _mapping_error(operation, "vendor timestamp is invalid") from exc


def _build[ModelT: CoreModel](
    model: type[ModelT], payload: dict[str, object], operation: str
) -> ModelT:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise _mapping_error(operation, "vendor data failed boundary validation") from exc


def _mapping_error(operation: str, message: str) -> MT5ClientError:
    return MT5ClientError(MT5ErrorCategory.DATA_MAPPING_ERROR, operation, message)


def map_terminal_health(
    terminal_raw: object,
    account_raw: object | None,
    terminal_version_raw: object | None,
    package_version: str,
    retrieved_at: datetime,
) -> MT5TerminalHealth:
    operation = "health_check"
    terminal = _mapping(terminal_raw, operation)
    terminal_version: str | None = None
    if isinstance(terminal_version_raw, tuple):
        terminal_version = ".".join(str(part) for part in terminal_version_raw)
    return _build(
        MT5TerminalHealth,
        {
            "retrieved_at": retrieved_at,
            "connection_state": (
                "CONNECTED" if _boolean(terminal, "connected", operation) else "DISCONNECTED"
            ),
            "authenticated": account_raw is not None,
            "package_version": package_version,
            "terminal_version": terminal_version,
            "terminal_build": _integer(terminal, "build", operation),
            "terminal_name": _text(terminal, "name", operation),
            "terminal_company": _text(terminal, "company", operation),
            "trade_api_disabled": _boolean(terminal, "tradeapi_disabled", operation),
        },
        operation,
    )


def map_account_info(raw: object, retrieved_at: datetime) -> MT5AccountInfo:
    operation = "get_account_info"
    data = _mapping(raw, operation)
    decimal_fields = {
        target: _decimal(data, source, operation)
        for target, source in {
            "balance": "balance",
            "credit": "credit",
            "profit": "profit",
            "equity": "equity",
            "margin": "margin",
            "margin_free": "margin_free",
            "margin_level": "margin_level",
            "margin_stop_out_call": "margin_so_call",
            "margin_stop_out_stop": "margin_so_so",
            "margin_initial": "margin_initial",
            "margin_maintenance": "margin_maintenance",
            "assets": "assets",
            "liabilities": "liabilities",
            "commission_blocked": "commission_blocked",
        }.items()
    }
    return _build(
        MT5AccountInfo,
        {
            "retrieved_at": retrieved_at,
            "account_id": _integer(data, "login", operation),
            "trade_mode": _integer(data, "trade_mode", operation),
            "leverage": _integer(data, "leverage", operation),
            "limit_orders": _integer(data, "limit_orders", operation),
            "margin_stop_out_mode": _integer(data, "margin_so_mode", operation),
            "trade_allowed": _boolean(data, "trade_allowed", operation),
            "expert_trading_allowed": _boolean(data, "trade_expert", operation),
            "margin_mode": _integer(data, "margin_mode", operation),
            "currency_digits": _integer(data, "currency_digits", operation),
            "fifo_close": _boolean(data, "fifo_close", operation),
            "currency": _text(data, "currency", operation),
            "server": _text(data, "server", operation),
            "company": _text(data, "company", operation),
            **decimal_fields,
        },
        operation,
    )


def map_symbol_summary(raw: object, retrieved_at: datetime) -> MT5SymbolSummary:
    operation = "get_symbols"
    data = _mapping(raw, operation)
    return _build(
        MT5SymbolSummary,
        {
            "retrieved_at": retrieved_at,
            "symbol": _text(data, "name", operation),
            "description": _text(data, "description", operation),
            "path": _text(data, "path", operation),
            "selected": _boolean(data, "select", operation),
            "visible": _boolean(data, "visible", operation),
        },
        operation,
    )


def map_symbol_info(raw: object, retrieved_at: datetime) -> MT5SymbolInfo:
    operation = "get_symbol_info"
    data = _mapping(raw, operation)
    return _build(
        MT5SymbolInfo,
        {
            "retrieved_at": retrieved_at,
            "symbol": _text(data, "name", operation),
            "description": _text(data, "description", operation),
            "path": _text(data, "path", operation),
            "selected": _boolean(data, "select", operation),
            "visible": _boolean(data, "visible", operation),
            "digits": _integer(data, "digits", operation),
            "point": _decimal(data, "point", operation),
            "trade_tick_size": _decimal(data, "trade_tick_size", operation),
            "trade_tick_value": _decimal(data, "trade_tick_value", operation),
            "trade_contract_size": _decimal(data, "trade_contract_size", operation),
            "volume_min": _decimal(data, "volume_min", operation),
            "volume_max": _decimal(data, "volume_max", operation),
            "volume_step": _decimal(data, "volume_step", operation),
            "trade_stops_level": _integer(data, "trade_stops_level", operation),
            "trade_freeze_level": _integer(data, "trade_freeze_level", operation),
            "currency_base": _text(data, "currency_base", operation),
            "currency_profit": _text(data, "currency_profit", operation),
            "trading_mode": _integer(data, "trade_mode", operation),
        },
        operation,
    )


def map_tick(raw: object, symbol: str, retrieved_at: datetime) -> MT5Tick:
    operation = "get_tick"
    data = _mapping(raw, operation)
    bid = _decimal(data, "bid", operation)
    ask = _decimal(data, "ask", operation)
    return _build(
        MT5Tick,
        {
            "retrieved_at": retrieved_at,
            "symbol": symbol,
            "source_time": _epoch_time(
                data,
                operation,
                seconds_field="time",
                milliseconds_field="time_msc",
            ),
            "bid": bid,
            "ask": ask,
            "spread": ask - bid,
            "last": _decimal(data, "last", operation),
            "volume": _decimal(data, "volume_real", operation),
            "flags": _integer(data, "flags", operation),
        },
        operation,
    )


def map_candle(
    raw: object,
    symbol: str,
    timeframe: Timeframe,
    retrieved_at: datetime,
) -> MT5Candle:
    operation = "get_candles"
    data = _mapping(raw, operation)
    return _build(
        MT5Candle,
        {
            "retrieved_at": retrieved_at,
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time": _epoch_time(data, operation, seconds_field="time"),
            "open": _decimal(data, "open", operation),
            "high": _decimal(data, "high", operation),
            "low": _decimal(data, "low", operation),
            "close": _decimal(data, "close", operation),
            "tick_volume": _integer(data, "tick_volume", operation),
            "broker_spread_points": _integer(data, "spread", operation),
            "real_volume": _integer(data, "real_volume", operation),
        },
        operation,
    )


def map_position(raw: object, retrieved_at: datetime) -> MT5OpenPosition:
    operation = "get_positions"
    data = _mapping(raw, operation)
    return _build(
        MT5OpenPosition,
        {
            "retrieved_at": retrieved_at,
            "ticket": _integer(data, "ticket", operation),
            "identifier": _integer(data, "identifier", operation),
            "symbol": _text(data, "symbol", operation),
            "side": _integer(data, "type", operation),
            "volume": _decimal(data, "volume", operation),
            "open_time": _epoch_time(
                data,
                operation,
                seconds_field="time",
                milliseconds_field="time_msc",
            ),
            "update_time": _epoch_time(
                data,
                operation,
                seconds_field="time_update",
                milliseconds_field="time_update_msc",
            ),
            "price_open": _decimal(data, "price_open", operation),
            "stop_loss": _decimal(data, "sl", operation),
            "take_profit": _decimal(data, "tp", operation),
            "price_current": _decimal(data, "price_current", operation),
            "swap": _decimal(data, "swap", operation),
            "profit": _decimal(data, "profit", operation),
            "magic": _integer(data, "magic", operation),
            "reason": _integer(data, "reason", operation),
            "comment": _text(data, "comment", operation),
            "external_id": _text(data, "external_id", operation),
        },
        operation,
    )
