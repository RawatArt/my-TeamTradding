"""Small structured-logging layer with defensive credential redaction."""

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import TextIO

from pydantic import BaseModel, SecretStr

_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)
_SENSITIVE_KEY_PARTS = (
    "account_id",
    "api_key",
    "credential",
    "login",
    "password",
    "secret",
    "server",
    "terminal_path",
    "token",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize(value: object, key: str | None = None) -> object:
    if key is not None and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, SecretStr):
        return "[REDACTED]"
    if isinstance(value, BaseModel):
        return _sanitize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    """Serialize log records as compact JSON with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = _sanitize(value, key)
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    level: str = "INFO",
    *,
    json_output: bool = True,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure and return the application's root logger."""
    logger = logging.getLogger("ai_trading_team")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(stream)
    formatter: logging.Formatter = JsonFormatter() if json_output else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger beneath the configured application namespace."""
    prefix = "ai_trading_team"
    return logging.getLogger(name if name.startswith(prefix) else f"{prefix}.{name}")
