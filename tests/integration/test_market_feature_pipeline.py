from ai_trading_team.features import MarketFeatureEngine, canonical_feature_json
from ai_trading_team.schemas.enums import FeatureAvailability
from tests.fakes.features import feature_snapshot


def test_complete_snapshot_to_feature_set_pipeline_is_deterministic() -> None:
    snapshot = feature_snapshot()
    engine = MarketFeatureEngine()

    first = engine.calculate(snapshot)
    second = engine.calculate(snapshot)

    assert first == second
    assert canonical_feature_json(first) == canonical_feature_json(second)
    assert first.timeframes.m15.trend.ema_200.status is FeatureAvailability.VALID
    assert first.timeframes.h1.trend.ema_200.status is FeatureAvailability.VALID
    assert first.timeframes.h4.trend.ema_200.status is FeatureAvailability.VALID
