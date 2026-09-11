"""Explicit deterministic replay clock with no wall-clock dependency."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.schemas.enums import ReplayErrorCategory
from ai_trading_team.schemas.historical import DatasetPartition


@dataclass(frozen=True, slots=True)
class ReplayClock:
    """Validated immutable schedule of scored decision instants."""

    schedule: tuple[datetime, ...]
    partition: DatasetPartition

    def __post_init__(self) -> None:
        normalized: list[datetime] = []
        for value in self.schedule:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ReplayError(
                    ReplayErrorCategory.INVALID_REPLAY_CLOCK,
                    "replay schedule timestamps must be timezone-aware",
                )
            normalized.append(value.astimezone(UTC))
        values = tuple(normalized)
        if not values or tuple(sorted(set(values))) != values:
            raise ReplayError(
                ReplayErrorCategory.INVALID_REPLAY_CLOCK,
                "replay schedule must be non-empty, unique, and strictly increasing",
            )
        if any(
            value < self.partition.evaluation_start
            or value >= self.partition.evaluation_end
            for value in values
        ):
            raise ReplayError(
                ReplayErrorCategory.PARTITION_VIOLATION,
                "replay schedule must remain inside the partition evaluation range",
            )
        object.__setattr__(self, "schedule", values)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.schedule)
