from datetime import timedelta

import pytest
from tests.fakes.features import feature_candles, feature_snapshot, generated_closes

from ai_trading_team.features import FeatureEngineError, MarketFeatureEngine
from ai_trading_team.features.indicators import adx_series, atr_series, ema_series, rsi_series
from ai_trading_team.schemas.enums import FeatureErrorCategory, Timeframe


@pytest.mark.parametrize("period", (20, 50, 200))
def test_ema_prefix_value_is_invariant_when_future_suffix_is_excluded(period: int) -> None:
    full = generated_closes(240)
    prefix_length = period + 10

    assert ema_series(full[:prefix_length], period)[-1] == ema_series(full, period)[
        prefix_length - 1
    ]


def test_rsi_prefix_value_is_invariant_when_future_suffix_is_excluded() -> None:
    full = generated_closes(100)
    prefix_length = 50

    assert rsi_series(full[:prefix_length], 14)[-1] == rsi_series(full, 14)[prefix_length - 1]


def test_atr_prefix_value_is_invariant_when_future_suffix_is_excluded() -> None:
    full = feature_candles(Timeframe.M15, 100)
    prefix_length = 50

    assert atr_series(full[:prefix_length], 14)[-1] == atr_series(full, 14)[prefix_length - 1]


def test_adx_prefix_value_is_invariant_when_future_suffix_is_excluded() -> None:
    full = feature_candles(Timeframe.M15, 100)
    prefix_length = 50

    assert adx_series(full[:prefix_length], 14)[-1] == adx_series(full, 14)[prefix_length - 1]


@pytest.mark.parametrize(
    ("open_offset_minutes", "category"),
    (
        (1, FeatureErrorCategory.FUTURE_CANDLE),
        (-5, FeatureErrorCategory.INCOMPLETE_CANDLE),
    ),
)
def test_future_or_incomplete_candle_prevents_feature_set_creation(
    open_offset_minutes: int,
    category: FeatureErrorCategory,
) -> None:
    snapshot = feature_snapshot()
    latest = snapshot.candles.m15[-1].model_copy(
        update={
            "open_time": snapshot.snapshot_completed_at
            + timedelta(minutes=open_offset_minutes)
        }
    )
    candles = snapshot.candles.model_copy(
        update={"m15": (*snapshot.candles.m15[:-1], latest)}
    )
    invalid = snapshot.model_copy(update={"candles": candles})

    with pytest.raises(FeatureEngineError) as caught:
        MarketFeatureEngine().calculate(invalid)

    assert caught.value.category is category


def test_duplicate_or_reordered_candle_time_prevents_calculation() -> None:
    snapshot = feature_snapshot()
    duplicate = snapshot.candles.m15[1].model_copy(
        update={"open_time": snapshot.candles.m15[0].open_time}
    )
    candles = snapshot.candles.model_copy(
        update={"m15": (snapshot.candles.m15[0], duplicate, *snapshot.candles.m15[2:])}
    )

    with pytest.raises(FeatureEngineError) as caught:
        MarketFeatureEngine().calculate(snapshot.model_copy(update={"candles": candles}))

    assert caught.value.category is FeatureErrorCategory.INVALID_CANDLE_ORDER
