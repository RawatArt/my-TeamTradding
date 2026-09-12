"""M9 completed-candle discovery tests."""

from datetime import timedelta
from decimal import Decimal

import pytest
from tests.fakes.market import SNAPSHOT_END, SYMBOL, FakeMarketDataSource, candles

from ai_trading_team.config import ContinuousShadowSettings
from ai_trading_team.observation import CompletedCandleDiscovery, ObservationRuntimeError
from ai_trading_team.observation.identifiers import decision_candle_content_digest
from ai_trading_team.schemas.enums import ObservationFailureCategory, Timeframe


def test_discovery_uses_completed_m15_read_and_stable_identity() -> None:
    source = FakeMarketDataSource()
    source.candle_results[Timeframe.M15] = candles(Timeframe.M15, 2)
    service = CompletedCandleDiscovery(
        source,
        ContinuousShadowSettings(discovery_lookback=2),
        SYMBOL,
        clock=lambda: SNAPSHOT_END,
    )

    first = service.poll()
    second = service.poll()

    assert first == second
    assert len(first) == 2
    assert first[-1].candle_close_at <= SNAPSHOT_END
    assert source.candle_calls[-1] == (SYMBOL, Timeframe.M15, 2, False)


def test_discovery_rejects_incomplete_candle_without_timezone_repair() -> None:
    source = FakeMarketDataSource()
    source.candle_results[Timeframe.M15] = candles(
        Timeframe.M15,
        1,
        latest_close=SNAPSHOT_END + timedelta(minutes=15),
    )
    service = CompletedCandleDiscovery(
        source,
        ContinuousShadowSettings(discovery_lookback=1),
        SYMBOL,
        clock=lambda: SNAPSHOT_END,
    )

    with pytest.raises(ObservationRuntimeError) as caught:
        service.poll()

    assert caught.value.category is ObservationFailureCategory.INVALID_COMPLETED_CANDLE


def test_decision_candle_digest_ignores_read_time_but_detects_revised_prices() -> None:
    candle = candles(Timeframe.M15, 1)[0]
    reread = candle.model_copy(
        update={"retrieved_at": candle.retrieved_at + timedelta(seconds=5)}
    )
    revised = candle.model_copy(update={"close": candle.close + Decimal("0.00001")})

    assert decision_candle_content_digest(candle) == decision_candle_content_digest(reread)
    assert decision_candle_content_digest(candle) != decision_candle_content_digest(revised)
