"""Tests for snapshot reproduction, deterministic identity, and decision freezing."""

from datetime import timedelta

import pytest
from tests.fakes.replay import (
    REPLAY_CUTOFF,
    replay_build,
    replay_proposal,
    replay_risk_decision,
)

from ai_trading_team.config import FeatureEngineSettings
from ai_trading_team.features import MarketFeatureEngine
from ai_trading_team.replay import ReplayError
from ai_trading_team.replay.engine import freeze_replay_decision
from ai_trading_team.replay.serialization import canonical_replay_bytes
from ai_trading_team.schemas.enums import FreshnessState, ReplayDecisionSource


def test_replay_build_reproduces_exact_m2_snapshot_and_m7_features() -> None:
    _, _, _, result = replay_build()
    assert result.snapshot.snapshot_completed_at == REPLAY_CUTOFF
    assert result.features == MarketFeatureEngine(FeatureEngineSettings()).calculate(
        result.snapshot
    )
    assert result.frame.market_snapshot.schema_version == result.snapshot.schema_version


def test_identical_replay_builds_have_equal_models_and_bytes() -> None:
    first = replay_build()[3]
    second = replay_build()[3]
    assert first == second
    assert canonical_replay_bytes(first) == canonical_replay_bytes(second)


def test_missing_candle_metadata_cannot_be_invented_for_snapshot() -> None:
    dataset, _, _, _ = replay_build()
    candles = tuple(
        candle.model_copy(update={"tick_volume": None})
        if candle.timeframe.value == "M15" and candle.close_time == REPLAY_CUTOFF
        else candle
        for candle in dataset.candles
    )
    from ai_trading_team.replay.serialization import dataset_digest

    changed = dataset.model_copy(update={"candles": candles})
    changed = changed.model_copy(update={"dataset_digest": dataset_digest(changed)})
    with pytest.raises(ReplayError):
        replay_build(changed)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("cycle_id", "different-cycle"),
        ("snapshot_id", "different-snapshot"),
        ("proposal_id", "different-proposal"),
        ("symbol", "GBPUSD"),
        ("schema_version", "2.0.0"),
    ),
)
def test_persisted_risk_decision_requires_exact_frozen_linkage(
    field: str, value: str
) -> None:
    _, _, _, result = replay_build()
    proposal = replay_proposal(result)
    risk = replay_risk_decision(result, proposal)
    frozen = freeze_replay_decision(
        result.frame,
        proposal,
        source=ReplayDecisionSource.PERSISTED_RECORD,
        frozen_at=REPLAY_CUTOFF,
        risk_decision=risk,
    )
    assert frozen.risk_link is not None

    mismatched = risk.model_copy(update={field: value})
    with pytest.raises(ReplayError, match="linkage"):
        freeze_replay_decision(
            result.frame,
            proposal,
            source=ReplayDecisionSource.PERSISTED_RECORD,
            frozen_at=REPLAY_CUTOFF,
            risk_decision=mismatched,
        )


def test_frozen_proposal_trace_mismatch_fails_closed() -> None:
    _, _, _, result = replay_build()
    proposal = replay_proposal(result).model_copy(update={"snapshot_id": "wrong-snapshot"})
    with pytest.raises(ReplayError):
        freeze_replay_decision(
            result.frame,
            proposal,
            source=ReplayDecisionSource.SCRIPTED,
            frozen_at=REPLAY_CUTOFF,
        )


def test_replay_time_must_belong_to_declared_schedule() -> None:
    dataset, source, configuration, _ = replay_build()
    from ai_trading_team.config import MarketDataSettings
    from ai_trading_team.replay.engine import HistoricalReplayEngine

    engine = HistoricalReplayEngine(
        source, MarketDataSettings(), FeatureEngineSettings()
    )
    with pytest.raises(ReplayError, match="schedule"):
        engine.build_frame(configuration, REPLAY_CUTOFF + timedelta(minutes=15))
    assert dataset.dataset_digest == configuration.dataset_digest


def test_stale_but_valid_historical_snapshot_is_preserved() -> None:
    from ai_trading_team.replay.serialization import dataset_digest

    dataset = replay_build()[0]
    observation = dataset.snapshot_observations[0]
    stale_tick = observation.tick.model_copy(
        update={"source_time": REPLAY_CUTOFF - timedelta(days=1)}
    )
    stale_observation = observation.model_copy(update={"tick": stale_tick})
    changed = dataset.model_copy(update={"snapshot_observations": (stale_observation,)})
    changed = changed.model_copy(update={"dataset_digest": dataset_digest(changed)})
    result = replay_build(changed)[3]
    assert result.snapshot.consistency.freshness.tick.state is FreshnessState.STALE
    assert result.features.source_freshness.tick.state is FreshnessState.STALE
