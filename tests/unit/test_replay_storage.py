"""Tests for sanitized append-only M8 persistence."""

import pytest
from tests.fakes.replay import PARTITION_ID, frozen_decision, replay_build

from ai_trading_team.evaluation import OutcomeEvaluator, summarize_performance
from ai_trading_team.replay import DuplicateReplayRecordError
from ai_trading_team.schemas.evaluation import PerformanceSummary, TradeOutcome
from ai_trading_team.schemas.replay import FrozenReplayDecision, ReplayConfiguration, ReplayFrame
from ai_trading_team.storage.replay import InMemoryReplayRepository, SQLiteReplayRepository


def _artifacts() -> tuple[
    ReplayConfiguration,
    ReplayFrame,
    FrozenReplayDecision,
    TradeOutcome,
    PerformanceSummary,
]:
    _, source, configuration, result = replay_build()
    frozen = frozen_decision(result)
    view = source.outcome_view(
        frozen,
        PARTITION_ID,
        configuration.outcome_timeframe,
        configuration.outcome_horizon,
    )
    outcome = OutcomeEvaluator().evaluate(result.frame, frozen, view, configuration)
    return configuration, result.frame, frozen, outcome, summarize_performance((outcome,))


@pytest.mark.parametrize("sqlite", [False, True])
def test_repository_is_append_only_and_partition_scoped(tmp_path, sqlite: bool) -> None:  # type: ignore[no-untyped-def]
    configuration, frame, frozen, outcome, summary = _artifacts()
    repository = (
        SQLiteReplayRepository(tmp_path / "replay.db")
        if sqlite
        else InMemoryReplayRepository()
    )
    repository.append_configuration(frame.replay_id, PARTITION_ID, configuration)
    repository.append_frame(frame)
    repository.append_decision(PARTITION_ID, frozen)
    repository.append_outcome(outcome)
    repository.append_summary(summary)
    stored = repository.get(frame.replay_id, PARTITION_ID, outcome.outcome_id)
    assert stored is not None and stored[0] == "OUTCOME"
    assert repository.get(frame.replay_id, "wrong-partition", outcome.outcome_id) is None
    with pytest.raises(DuplicateReplayRecordError):
        repository.append_outcome(outcome)
    if isinstance(repository, SQLiteReplayRepository):
        repository.close()
