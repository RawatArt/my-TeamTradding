"""Sanitized typed M9 errors."""

from ai_trading_team.schemas.enums import ObservationFailureCategory


class ObservationRuntimeError(RuntimeError):
    """Failure carrying a stable category and non-sensitive message."""

    def __init__(self, category: ObservationFailureCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


class DuplicateDecisionError(ObservationRuntimeError):
    def __init__(self) -> None:
        super().__init__(
            ObservationFailureCategory.DUPLICATE_CANDLE,
            "decision candle has already been recorded",
        )
