"""Canonical deterministic M8 serialization and digest helpers."""

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from ai_trading_team.features.serialization import (
    canonical_decimal,
    canonical_json_bytes,
    canonical_timestamp,
)
from ai_trading_team.schemas.common import ContentDigest
from ai_trading_team.schemas.historical import HistoricalDataset


def canonical_value(value: Any) -> Any:
    """Convert supported boundary values to canonical JSON-compatible values."""
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, timedelta):
        return f"{_duration_microseconds(value)}us"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_value(item) for item in value]
    return value


def canonical_replay_bytes(value: Any) -> bytes:
    """Return compact, sorted UTF-8 bytes for one supported replay value."""
    return canonical_json_bytes(canonical_value(value))


def content_digest(value: Any) -> ContentDigest:
    """Return a versioned SHA-256 identity for canonical replay bytes."""
    return f"sha256:{hashlib.sha256(canonical_replay_bytes(value)).hexdigest()}"


def dataset_digest(dataset: HistoricalDataset) -> ContentDigest:
    """Hash every dataset field except the self-referential declared digest."""
    return content_digest(
        {
            "canonicalization_version": "1.0.0",
            "schema_version": dataset.schema_version,
            "metadata": dataset.metadata,
            "candles": dataset.candles,
            "snapshot_observations": dataset.snapshot_observations,
        }
    )


def _duration_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )
