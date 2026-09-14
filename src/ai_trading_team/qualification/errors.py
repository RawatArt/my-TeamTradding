"""Sanitized M10 qualification errors."""

from ai_trading_team.schemas.enums import QualificationErrorCategory


class QualificationError(RuntimeError):
    def __init__(self, category: QualificationErrorCategory, message: str) -> None:
        self.category = category
        super().__init__(message)

