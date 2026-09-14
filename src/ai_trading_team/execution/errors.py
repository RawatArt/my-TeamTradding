"""Sanitized M11 execution failures."""

from ai_trading_team.schemas.enums import DemoExecutionFailureCategory


class DemoExecutionError(RuntimeError):
    """A typed failure that never contains credentials or raw broker payloads."""

    def __init__(
        self,
        category: DemoExecutionFailureCategory,
        message: str,
        *,
        dispatch_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.dispatch_uncertain = dispatch_uncertain

    def __str__(self) -> str:
        return f"{self.category.value}: {self.message}"
