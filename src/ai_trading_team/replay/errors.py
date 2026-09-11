"""Sanitized typed M8 replay failures."""

from ai_trading_team.schemas.enums import ReplayErrorCategory


class ReplayError(RuntimeError):
    """Failure that prevents a valid replay artifact without leaking source data."""

    def __init__(self, category: ReplayErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


class DuplicateReplayRecordError(ReplayError):
    """Raised when an append-only identity is reused."""

    def __init__(self) -> None:
        super().__init__(
            ReplayErrorCategory.DUPLICATE_REPLAY_RECORD,
            "replay record identity already exists",
        )
