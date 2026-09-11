"""Sanitized typed errors for structural M7 feature failures."""

from ai_trading_team.schemas.enums import FeatureErrorCategory


class FeatureEngineError(RuntimeError):
    """A safe failure that never embeds source prices or sensitive account data."""

    def __init__(self, category: FeatureErrorCategory, detail: str) -> None:
        super().__init__(detail)
        self.category = category
        self.detail = detail

