from datetime import timedelta
from decimal import Decimal

import pytest
from tests.fakes.features import feature_candles

from ai_trading_team.config import FeatureEngineSettings
from ai_trading_team.features.serialization import (
    canonical_decimal,
    canonical_timestamp,
    configuration_digest,
    source_candle_digest,
)
from ai_trading_team.schemas.enums import Timeframe


def test_known_source_candle_digest_is_stable() -> None:
    digest = source_candle_digest(
        "EURUSD.a", Timeframe.M15, feature_candles(Timeframe.M15, 1)
    )

    assert digest == "sha256:18cad6cca679c26adbfae77d0748ff2250cac6a69ccf9ebc1e230842bb5a2b4e"


def test_source_digest_covers_every_candle_field_and_collection_identity() -> None:
    candle = feature_candles(Timeframe.M15, 1)[0]
    baseline = source_candle_digest("EURUSD.a", Timeframe.M15, (candle,))
    mutations = (
        {"schema_version": "1.0.1"},
        {"retrieved_at": candle.retrieved_at + timedelta(microseconds=1)},
        {"symbol": "OTHER"},
        {"timeframe": Timeframe.H1},
        {"open_time": candle.open_time + timedelta(microseconds=1)},
        {"open": candle.open + Decimal("0.00001")},
        {"high": candle.high + Decimal("0.00001")},
        {"low": candle.low - Decimal("0.00001")},
        {"close": candle.close + Decimal("0.00001")},
        {"tick_volume": candle.tick_volume + 1},
        {"broker_spread_points": candle.broker_spread_points + 1},
        {"real_volume": candle.real_volume + 1},
    )

    assert all(
        source_candle_digest(
            "EURUSD.a", Timeframe.M15, (candle.model_copy(update=mutation),)
        )
        != baseline
        for mutation in mutations
    )
    assert source_candle_digest("OTHER", Timeframe.M15, (candle,)) != baseline
    assert source_candle_digest("EURUSD.a", Timeframe.H1, (candle,)) != baseline


def test_source_digest_is_order_sensitive() -> None:
    candles = feature_candles(Timeframe.M15, 2)

    assert source_candle_digest(
        "EURUSD.a", Timeframe.M15, candles
    ) != source_candle_digest("EURUSD.a", Timeframe.M15, tuple(reversed(candles)))


def test_decimal_and_timestamp_canonicalization_are_explicit() -> None:
    candle = feature_candles(Timeframe.M15, 1)[0]

    assert canonical_decimal(Decimal("1.23000")) == "1.23"
    assert canonical_decimal(Decimal("-0.000")) == "0"
    assert canonical_timestamp(candle.open_time).endswith(".000000Z")
    with pytest.raises(ValueError, match="finite"):
        canonical_decimal(Decimal("NaN"))


def test_known_configuration_digest_is_stable_and_covers_all_choices() -> None:
    settings = FeatureEngineSettings()
    baseline = configuration_digest(settings)

    assert baseline == "sha256:a1b4b6c0c04c848d9ed877eebd9e3e1ee8de0a0db5c4e1bc3b578484303af9de"
    assert configuration_digest(
        settings.model_copy(update={"recent_range_lookback": 21})
    ) != baseline
    assert configuration_digest(settings.model_copy(update={"swing_left_bars": 3})) != baseline
    assert configuration_digest(settings.model_copy(update={"swing_right_bars": 3})) != baseline
    assert configuration_digest(
        settings.model_copy(update={"configuration_version": "1.0.1"})
    ) != baseline
