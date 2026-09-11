from datetime import timedelta
from decimal import Decimal

import pytest
from tests.fakes.features import feature_candles, feature_snapshot

from ai_trading_team.config import FeatureEngineSettings
from ai_trading_team.features import FeatureEngineError, MarketFeatureEngine, canonical_feature_json
from ai_trading_team.schemas.enums import (
    FeatureAvailability,
    FeatureErrorCategory,
    FreshnessState,
    Timeframe,
)
from ai_trading_team.schemas.market import ObservationFreshness, SnapshotFreshness
from ai_trading_team.schemas.timeframes import timeframe_duration


def test_complete_snapshot_produces_traceable_multi_timeframe_features() -> None:
    snapshot = feature_snapshot()
    result = MarketFeatureEngine().calculate(snapshot)

    assert result.cycle_id == snapshot.cycle_id
    assert result.snapshot_id == snapshot.snapshot_id
    assert result.symbol == snapshot.symbol
    assert result.primary_timeframe is Timeframe.M15
    assert result.generated_at == snapshot.snapshot_completed_at
    assert result.feature_set_version == "1.0.0"
    assert result.feature_engine_version == "1.0.0"
    assert result.timeframes.m15.source_candle_count == 200
    assert result.timeframes.h1.timeframe is Timeframe.H1
    assert result.timeframes.h4.timeframe is Timeframe.H4
    assert result.timeframes.m15.trend.ema_200.status is FeatureAvailability.VALID
    assert result.timeframes.m15.trend.ema_200.required_candles == 200
    assert isinstance(result.timeframes.m15.trend.ema_200.value, Decimal)
    assert result.timeframes.m15.market_structure.recent_swing_high.status is (
        FeatureAvailability.VALID
    )


def test_required_history_is_explicit_and_distances_inherit_reference_status() -> None:
    result = MarketFeatureEngine().calculate(feature_snapshot(10)).timeframes.m15

    assert result.candle_geometry.candle_range.required_candles == 1
    assert result.trend.ema_20.required_candles == 20
    assert result.trend.ema_50.required_candles == 50
    assert result.trend.ema_200.required_candles == 200
    assert result.momentum.rsi_14.required_candles == 15
    assert result.volatility.atr_14.required_candles == 15
    assert result.trend_strength.adx_14.required_candles == 28
    assert result.market_structure.recent_range_high.required_candles == 20
    assert result.market_structure.recent_swing_high.required_candles == 5
    dependent_pairs = (
        (result.trend.ema_20, result.trend.distance_from_ema_20),
        (result.trend.ema_50, result.trend.distance_from_ema_50),
        (result.trend.ema_200, result.trend.distance_from_ema_200),
        (
            result.market_structure.recent_swing_high,
            result.market_structure.distance_from_recent_swing_high,
        ),
        (
            result.market_structure.recent_swing_low,
            result.market_structure.distance_from_recent_swing_low,
        ),
        (
            result.market_structure.recent_range_high,
            result.market_structure.distance_from_recent_range_high,
        ),
        (
            result.market_structure.recent_range_low,
            result.market_structure.distance_from_recent_range_low,
        ),
    )
    for reference, distance in dependent_pairs:
        assert distance.status is reference.status
        assert distance.required_candles == reference.required_candles
        assert distance.available_candles == reference.available_candles
    geometry_features = (
        result.candle_geometry.candle_range,
        result.candle_geometry.real_body,
        result.candle_geometry.upper_wick,
        result.candle_geometry.lower_wick,
        result.candle_geometry.body_range_ratio,
    )
    assert all(item.required_candles == 1 for item in geometry_features)
    assert all(item.status is FeatureAvailability.VALID for item in geometry_features)
    assert result.trend.distance_from_ema_20.required_candles == 20
    assert result.trend.distance_from_ema_50.required_candles == 50
    assert result.trend.distance_from_ema_200.required_candles == 200
    assert result.market_structure.recent_range_low.required_candles == 20
    assert result.market_structure.distance_from_recent_range_high.required_candles == 20
    assert result.market_structure.distance_from_recent_range_low.required_candles == 20
    assert result.market_structure.recent_swing_low.required_candles == 5
    assert result.market_structure.distance_from_recent_swing_high.required_candles == 5
    assert result.market_structure.distance_from_recent_swing_low.required_candles == 5


def test_custom_structure_windows_control_required_history() -> None:
    result = MarketFeatureEngine(
        FeatureEngineSettings(
            recent_range_lookback=7,
            swing_left_bars=3,
            swing_right_bars=4,
        )
    ).calculate(feature_snapshot(10)).timeframes.m15

    assert result.market_structure.recent_range_high.required_candles == 7
    assert result.market_structure.recent_swing_high.required_candles == 8


def test_timeframe_provenance_uses_explicit_open_and_close_timestamps() -> None:
    snapshot = feature_snapshot()
    result = MarketFeatureEngine().calculate(snapshot).timeframes.m15
    candles = snapshot.candles.m15

    assert result.source_first_candle_open_at == candles[0].open_time
    assert result.source_last_candle_open_at == candles[-1].open_time
    assert result.source_last_candle_close_at == (
        candles[-1].open_time + timeframe_duration(Timeframe.M15)
    )
    assert result.evaluation_candle_open_at == candles[-1].open_time


def test_repeated_calculation_has_equal_models_and_canonical_json() -> None:
    snapshot = feature_snapshot()
    engine = MarketFeatureEngine()

    first = engine.calculate(snapshot)
    second = engine.calculate(snapshot)

    assert first == second
    assert canonical_feature_json(first) == canonical_feature_json(second)


def test_distances_are_signed_latest_close_minus_reference_price() -> None:
    snapshot = feature_snapshot()
    result = MarketFeatureEngine().calculate(snapshot).timeframes.m15
    ema = result.trend.ema_20
    distance = result.trend.distance_from_ema_20

    assert ema.value is not None and distance.value is not None
    assert distance.value == snapshot.candles.m15[-1].close - ema.value


def test_stale_but_valid_snapshot_produces_features_and_preserves_freshness() -> None:
    snapshot = feature_snapshot()
    original = snapshot.consistency.freshness
    stale_tick = ObservationFreshness(
        observed_at=original.tick.observed_at,
        evaluated_at=original.tick.evaluated_at,
        age=original.tick.age,
        maximum_age=timedelta(seconds=1),
        state=FreshnessState.STALE,
    )
    freshness = SnapshotFreshness(
        tick=stale_tick,
        account=original.account,
        m15_candles=original.m15_candles,
        h1_candles=original.h1_candles,
        h4_candles=original.h4_candles,
        overall=FreshnessState.STALE,
    )
    stale = snapshot.model_copy(
        update={
            "consistency": snapshot.consistency.model_copy(update={"freshness": freshness})
        }
    )

    result = MarketFeatureEngine().calculate(stale)

    assert result.source_freshness.overall is FreshnessState.STALE
    assert any(warning.code.value == "STALE_SOURCE" for warning in result.warnings)


def test_absence_of_confirmed_swing_is_unavailable_not_zero() -> None:
    collections = {
        timeframe: feature_candles(
            timeframe,
            200,
            closes=(Decimal("1.10000"),) * 200,
        )
        for timeframe in (Timeframe.M15, Timeframe.H1, Timeframe.H4)
    }
    result = MarketFeatureEngine().calculate(
        feature_snapshot(collections=collections)
    ).timeframes.m15

    assert result.market_structure.recent_swing_high.status is FeatureAvailability.UNAVAILABLE
    assert result.market_structure.recent_swing_high.value is None
    assert (
        result.market_structure.distance_from_recent_swing_high.status
        is FeatureAvailability.UNAVAILABLE
    )
    assert result.market_structure.distance_from_recent_swing_high.value is None


def test_invalid_constructed_configuration_fails_with_typed_error() -> None:
    invalid = FeatureEngineSettings.model_construct(
        configuration_version="1.0.0",
        recent_range_lookback=0,
        swing_left_bars=2,
        swing_right_bars=2,
    )

    with pytest.raises(FeatureEngineError) as caught:
        MarketFeatureEngine(invalid)

    assert caught.value.category is FeatureErrorCategory.CONFIGURATION_INCOMPATIBLE


def test_timeframes_are_calculated_independently() -> None:
    baseline = feature_snapshot()
    changed_h1 = feature_candles(
        Timeframe.H1,
        200,
        closes=(Decimal("2.00000"),) * 200,
    )
    changed = feature_snapshot(
        collections={
            Timeframe.M15: baseline.candles.m15,
            Timeframe.H1: changed_h1,
            Timeframe.H4: baseline.candles.h4,
        }
    )

    first = MarketFeatureEngine().calculate(baseline)
    second = MarketFeatureEngine().calculate(changed)

    assert first.timeframes.m15 == second.timeframes.m15
    assert first.timeframes.h4 == second.timeframes.h4
    assert first.timeframes.h1 != second.timeframes.h1


@pytest.mark.parametrize(
    ("update", "category"),
    (
        ({"symbol": "OTHER"}, FeatureErrorCategory.SYMBOL_MISMATCH),
        ({"timeframe": Timeframe.H1}, FeatureErrorCategory.TIMEFRAME_MISMATCH),
    ),
)
def test_structural_candle_identity_errors_fail_without_feature_set(
    update: dict[str, object], category: FeatureErrorCategory
) -> None:
    snapshot = feature_snapshot()
    changed = snapshot.candles.m15[0].model_copy(update=update)
    candles = snapshot.candles.model_copy(
        update={"m15": (changed, *snapshot.candles.m15[1:])}
    )
    invalid = snapshot.model_copy(update={"candles": candles})

    with pytest.raises(FeatureEngineError) as caught:
        MarketFeatureEngine().calculate(invalid)

    assert caught.value.category is category
    assert "EURUSD" not in caught.value.detail
