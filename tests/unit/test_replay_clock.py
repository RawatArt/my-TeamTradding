"""Tests for explicit M8 replay time."""

from datetime import timedelta

import pytest
from tests.fakes.replay import REPLAY_CUTOFF, replay_dataset

from ai_trading_team.replay import ReplayClock, ReplayError


def test_replay_clock_accepts_strict_utc_evaluation_schedule() -> None:
    partition = replay_dataset().metadata.partitions[0]
    clock = ReplayClock(
        (REPLAY_CUTOFF, REPLAY_CUTOFF + timedelta(minutes=15)), partition
    )
    assert tuple(clock) == clock.schedule


@pytest.mark.parametrize(
    "schedule",
    [
        (REPLAY_CUTOFF.replace(tzinfo=None),),
        (REPLAY_CUTOFF, REPLAY_CUTOFF),
        (REPLAY_CUTOFF + timedelta(minutes=15), REPLAY_CUTOFF),
    ],
)
def test_replay_clock_rejects_ambiguous_time(schedule: tuple) -> None:  # type: ignore[type-arg]
    with pytest.raises(ReplayError):
        ReplayClock(schedule, replay_dataset().metadata.partitions[0])


def test_warmup_time_cannot_become_scored_replay_frame() -> None:
    partition = replay_dataset().metadata.partitions[0]
    with pytest.raises(ReplayError, match="evaluation range"):
        ReplayClock((partition.evaluation_start - timedelta(minutes=15),), partition)
