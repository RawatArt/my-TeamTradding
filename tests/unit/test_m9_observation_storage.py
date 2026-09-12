"""M9 durable claim and binding tests."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.fakes.features import feature_snapshot

from ai_trading_team.observation.identifiers import (
    cycle_id_for_decision,
    decision_candle_content_digest,
    decision_key,
)
from ai_trading_team.schemas.enums import (
    DecisionClaimState,
    ObservationFailureCategory,
    Timeframe,
)
from ai_trading_team.schemas.observation import CompletedDecisionCandle
from ai_trading_team.schemas.timeframes import timeframe_duration
from ai_trading_team.storage.observation import (
    InMemoryObservationRepository,
    SQLiteObservationRepository,
)


def _candle() -> CompletedDecisionCandle:
    source = feature_snapshot().candles.m15[-1]
    close = source.open_time + timeframe_duration(Timeframe.M15)
    key = decision_key(source.symbol, Timeframe.M15, source.open_time, close)
    return CompletedDecisionCandle(
        decision_key=key,
        cycle_id=cycle_id_for_decision(key),
        symbol=source.symbol,
        candle_open_at=source.open_time,
        candle_close_at=close,
        candle_digest=decision_candle_content_digest(source),
        observed_at=close + timedelta(seconds=1),
    )


def test_claim_binds_actual_snapshot_once_and_duplicate_poll_does_not_reclaim() -> None:
    repository = InMemoryObservationRepository()
    candle = _candle()
    discovered = repository.discover(candle)
    assert repository.discover(candle) == discovered

    repository.claim(candle.decision_key, at=candle.observed_at)
    bound = repository.bind_snapshot(
        candle.decision_key,
        "snapshot-actual-m2-accepted",
        at=candle.observed_at,
    )
    repository.mark_processing(candle.decision_key, at=candle.observed_at)
    repository.mark_terminal(
        candle.decision_key,
        DecisionClaimState.COMPLETED,
        at=candle.observed_at,
    )

    assert bound.actual_snapshot_id == "snapshot-actual-m2-accepted"
    with pytest.raises(ValueError, match="DISCOVERED"):
        repository.claim(candle.decision_key, at=candle.observed_at)


def test_restart_abandons_claim_and_never_auto_resumes() -> None:
    repository = InMemoryObservationRepository()
    candle = _candle()
    repository.discover(candle)
    repository.claim(candle.decision_key, at=candle.observed_at)

    recovered = repository.recover_incomplete(at=candle.observed_at + timedelta(seconds=1))

    assert recovered[0].state is DecisionClaimState.ABANDONED
    assert recovered[0].failure_category is ObservationFailureCategory.PROCESS_RESTART
    with pytest.raises(ValueError, match="DISCOVERED"):
        repository.claim(candle.decision_key, at=candle.observed_at)


def test_sqlite_claim_survives_restart_as_abandoned(tmp_path: Path) -> None:
    path = tmp_path.joinpath("observation.sqlite3")
    candle = _candle()
    first = SQLiteObservationRepository(path)
    first.discover(candle)
    first.claim(candle.decision_key, at=candle.observed_at)
    first.close()

    second = SQLiteObservationRepository(path)
    recovered = second.recover_incomplete(at=candle.observed_at + timedelta(seconds=1))
    second.close()

    assert recovered[0].state is DecisionClaimState.ABANDONED
