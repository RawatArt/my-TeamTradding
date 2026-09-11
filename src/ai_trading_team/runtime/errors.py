"""Sanitized runtime/provider failures and retry classification."""

from ai_trading_team.schemas.enums import RuntimeFailureCategory


class RuntimeInvocationError(RuntimeError):
    """Known safe runtime rejection carrying no credentials or provider payload."""

    def __init__(self, category: RuntimeFailureCategory, detail: str) -> None:
        super().__init__(detail)
        self.category = category
        self.detail = detail


class ProviderError(RuntimeInvocationError):
    """Normalized provider failure with explicit dispatch/retry semantics."""

    def __init__(
        self,
        category: RuntimeFailureCategory,
        detail: str,
        *,
        retryable: bool,
        dispatch_occurred: bool,
    ) -> None:
        super().__init__(category, detail)
        self.retryable = retryable
        self.dispatch_occurred = dispatch_occurred
