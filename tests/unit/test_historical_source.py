"""Tests for dataset sealing, capped views, and partition isolation."""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from tests.fakes.market import SYMBOL
from tests.fakes.replay import (
    PARTITION_ID,
    REPLAY_CUTOFF,
    frozen_decision,
    replay_build,
    replay_dataset,
)

from ai_trading_team.replay import ReplayError
from ai_trading_team.replay.source import InMemoryHistoricalMarketDataSource
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.historical import HistoricalDataset
from ai_trading_team.schemas.replay import OutcomeHorizon


def test_dataset_digest_mismatch_fails_closed() -> None:
    dataset = replay_dataset().model_copy(update={"dataset_digest": "sha256:" + "f" * 64})
    with pytest.raises(ReplayError, match="digest"):
        InMemoryHistoricalMarketDataSource(dataset)


def test_decision_view_exposes_only_completed_candles_at_cutoff() -> None:
    source = InMemoryHistoricalMarketDataSource(replay_dataset())
    view = source.decision_view(PARTITION_ID, REPLAY_CUTOFF)
    candles = view.completed_candles(SYMBOL, Timeframe.M15, 500)
    assert candles[-1].close_time == REPLAY_CUTOFF
    assert all(candle.close_time <= REPLAY_CUTOFF for candle in candles)
    assert not hasattr(view, "outcome_view")
    assert not hasattr(view, "future_candles")


def test_outcome_view_starts_with_wholly_post_decision_candle() -> None:
    _, source, configuration, result = replay_build()
    frozen = frozen_decision(result)
    view = source.outcome_view(
        frozen,
        PARTITION_ID,
        Timeframe.M15,
        configuration.outcome_horizon,
    )
    assert view.candles[0].open_time == REPLAY_CUTOFF
    assert all(candle.open_time >= REPLAY_CUTOFF for candle in view.candles)


def test_partition_evaluation_end_caps_outcome_window() -> None:
    dataset, source, _, result = replay_build()
    partition = dataset.metadata.partitions[0]
    frozen = frozen_decision(result)
    view = source.outcome_view(
        frozen,
        PARTITION_ID,
        Timeframe.M15,
        OutcomeHorizon(max_elapsed=timedelta(days=365), max_bars=None),
    )
    assert all(candle.close_time <= partition.evaluation_end for candle in view.candles)


def test_decision_view_can_use_declared_context_warmup() -> None:
    dataset = replay_dataset()
    view = InMemoryHistoricalMarketDataSource(dataset).decision_view(
        PARTITION_ID, REPLAY_CUTOFF
    )
    candles = view.completed_candles(SYMBOL, Timeframe.H4, 200)
    assert candles[0].open_time < dataset.metadata.partitions[0].evaluation_start
    assert candles[-1].close_time == REPLAY_CUTOFF


def test_dataset_rejects_duplicate_candle_market_key_even_with_distinct_record_id() -> None:
    dataset = replay_dataset()
    duplicate = dataset.candles[0].model_copy(update={"source_record_id": "distinct-record"})
    payload = dataset.model_dump()
    payload["candles"] = (dataset.candles[0], duplicate, *dataset.candles[1:])
    with pytest.raises(ValidationError, match="open-time keys"):
        HistoricalDataset.model_validate(payload)


def test_dataset_rejects_duplicate_observation_as_of_key() -> None:
    dataset = replay_dataset()
    duplicate = dataset.snapshot_observations[0].model_copy(
        update={"observation_id": "distinct-observation"}
    )
    payload = dataset.model_dump()
    payload["snapshot_observations"] = (dataset.snapshot_observations[0], duplicate)
    with pytest.raises(ValidationError, match="effective-time keys"):
        HistoricalDataset.model_validate(payload)
