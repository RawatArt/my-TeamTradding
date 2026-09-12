"""Deterministic M9 decision identities and opaque snapshot-ID allocation."""

import hashlib
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from ai_trading_team.features.serialization import (
    canonical_decimal,
    canonical_json_bytes,
    canonical_timestamp,
)
from ai_trading_team.schemas.common import ContentDigest, CycleId, Identifier, SnapshotId
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.mt5 import MT5Candle


def decision_key(
    symbol: str,
    timeframe: Timeframe,
    candle_open_at: datetime,
    candle_close_at: datetime,
) -> Identifier:
    payload = {
        "identity_version": "1.0.0",
        "symbol": symbol,
        "timeframe": timeframe.value,
        "candle_open_at": canonical_timestamp(candle_open_at),
        "candle_close_at": canonical_timestamp(candle_close_at),
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"decision-m9-{digest}"


def cycle_id_for_decision(key: str) -> CycleId:
    return f"cycle-m9-{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def decision_candle_content_digest(candle: MT5Candle) -> ContentDigest:
    """Hash stable candle content while deliberately excluding retrieval time."""
    payload = {
        "identity_version": "1.0.0",
        "schema_version": candle.schema_version,
        "symbol": candle.symbol,
        "timeframe": candle.timeframe.value,
        "open_time": canonical_timestamp(candle.open_time),
        "open": canonical_decimal(candle.open),
        "high": canonical_decimal(candle.high),
        "low": canonical_decimal(candle.low),
        "close": canonical_decimal(candle.close),
        "tick_volume": candle.tick_volume,
        "broker_spread_points": candle.broker_spread_points,
        "real_volume": candle.real_volume,
    }
    return f"sha256:{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"


def record_id_for_decision(key: str) -> Identifier:
    return f"record-m9-{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def random_snapshot_id() -> SnapshotId:
    """Allocate an opaque ID; it has no derivation from decision-candle identity."""
    return f"snapshot-m9-{uuid4().hex}"


SnapshotIdFactory = Callable[[], SnapshotId]
