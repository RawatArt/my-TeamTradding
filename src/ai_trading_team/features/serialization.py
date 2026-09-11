"""Canonical JSON and digest construction for M7 feature provenance."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from ai_trading_team.config.settings import FeatureEngineSettings
from ai_trading_team.features.definitions import CANONICALIZATION_VERSION
from ai_trading_team.schemas.common import ContentDigest, CoreModel
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.features import MarketFeatureSet
from ai_trading_team.schemas.mt5 import MT5Candle


def canonical_decimal(value: Decimal) -> str:
    """Serialize a finite Decimal without exponent, insignificant zeros, or signed zero."""
    if not value.is_finite():
        raise ValueError("canonical Decimal must be finite")
    if value.is_zero():
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def canonical_timestamp(value: datetime) -> str:
    """Serialize one aware timestamp as fixed-width UTC with a Z suffix."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize an already JSON-compatible value to deterministic UTF-8 bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_model_bytes(model: CoreModel) -> bytes:
    """Serialize a strict boundary model using stable JSON-mode representations."""
    return canonical_json_bytes(model.model_dump(mode="json"))


def canonical_feature_json(feature_set: MarketFeatureSet) -> bytes:
    """Return the canonical byte representation used for reproducibility checks."""
    return canonical_model_bytes(feature_set)


def source_candle_digest(
    symbol: str,
    timeframe: Timeframe,
    candles: tuple[MT5Candle, ...],
) -> ContentDigest:
    """Hash every accepted source-candle field in chronological order.

    Identity is carried both at collection level and per candle. Decimal values use
    ``canonical_decimal`` and timestamps use fixed-width UTC ``canonical_timestamp``.
    """
    payload = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "symbol": symbol,
        "timeframe": timeframe.value,
        "candles": [
            {
                "schema_version": candle.schema_version,
                "retrieved_at": canonical_timestamp(candle.retrieved_at),
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
            for candle in candles
        ],
    }
    return _digest(payload)


def configuration_digest(settings: FeatureEngineSettings) -> ContentDigest:
    """Hash the complete versioned, non-secret feature configuration."""
    payload = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "configuration": {
            "configuration_version": settings.configuration_version,
            "recent_range_lookback": settings.recent_range_lookback,
            "swing_left_bars": settings.swing_left_bars,
            "swing_right_bars": settings.swing_right_bars,
        },
    }
    return _digest(payload)


def _digest(payload: object) -> ContentDigest:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"
