"""Temporary sanitized diagnostic for M1 read-only MetaTrader 5 connectivity."""

from __future__ import annotations

import json
import logging
import platform
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from pydantic import BaseModel, SecretStr

from ai_trading_team.config import AppSettings
from ai_trading_team.mt5 import MT5ClientError, MT5ReadOnlyClient

_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {
        "account_id",
        "login",
        "mt5_login",
        "mt5_password",
        "mt5_server",
        "password",
        "server",
        "terminal_path",
    }
)


def _sanitize(value: object, *, key: str | None = None) -> object:
    """Convert diagnostic values to JSON-safe data and redact sensitive metadata."""
    if key is not None and key.casefold() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, SecretStr):
        return _REDACTED
    if isinstance(value, BaseModel):
        return _sanitize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Enum):
        return _sanitize(value.value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _emit(name: str, value: object) -> None:
    """Print one deterministic, sanitized JSON diagnostic line."""
    print(json.dumps({"diagnostic": name, "value": _sanitize(value)}, ensure_ascii=False))


def _safe_error(error: MT5ClientError) -> dict[str, object]:
    """Return only structured error fields already sanitized by the adapter."""
    return {
        "category": error.category.value,
        "operation": error.operation,
        "vendor_code": error.vendor_code,
        "message": error.safe_message,
    }


def _quiet_logger() -> logging.Logger:
    """Prevent adapter log handlers from adding non-diagnostic output to this script."""
    logger = logging.getLogger("ai_trading_team.mt5_diagnostic")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def main() -> int:
    """Run sanitized read-only diagnostics and return a process status code."""
    settings = AppSettings()
    client = MT5ReadOnlyClient(settings.mt5, logger=_quiet_logger())

    _emit("python_executable", sys.executable)
    _emit("python_version", platform.python_version())
    try:
        package_version = version("MetaTrader5")
    except PackageNotFoundError:
        package_version = "unavailable"
    _emit("MetaTrader5_package_version", package_version)
    _emit(
        "configured_terminal_path",
        _REDACTED if settings.mt5.terminal_path is not None else "not configured",
    )

    exit_code = 0
    try:
        try:
            health = client.initialize()
        except MT5ClientError as error:
            _emit("initialize()", False)
            _emit("last_error()", _safe_error(error))
            _emit("terminal_info()", None)
            _emit("account_info()", None)
            _emit("version()", None)
            exit_code = 1
        else:
            _emit("initialize()", True)
            _emit("terminal_info()", health)
            _emit("version()", health.terminal_version)
            try:
                account = client.get_account_info()
            except MT5ClientError as error:
                _emit("account_info()", {"error": _safe_error(error)})
                exit_code = 1
            else:
                _emit("account_info()", account)
    finally:
        try:
            client.shutdown()
        except MT5ClientError as error:
            _emit("last_error()", _safe_error(error))
            exit_code = 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
