"""Structured errors for read-only MetaTrader 5 operations."""

from enum import StrEnum


class MT5ErrorCategory(StrEnum):
    """Stable failure categories exposed by the read-only adapter."""

    DEPENDENCY_UNAVAILABLE = "MT5_DEPENDENCY_UNAVAILABLE"
    NOT_INITIALIZED = "MT5_NOT_INITIALIZED"
    INITIALIZATION_ERROR = "MT5_INITIALIZATION_ERROR"
    AUTHENTICATION_ERROR = "MT5_AUTHENTICATION_ERROR"
    TERMINAL_UNAVAILABLE = "MT5_TERMINAL_UNAVAILABLE"
    ACCOUNT_INFO_ERROR = "MT5_ACCOUNT_INFO_ERROR"
    SYMBOL_UNAVAILABLE = "MT5_SYMBOL_UNAVAILABLE"
    SYMBOL_NOT_SELECTED = "MT5_SYMBOL_NOT_SELECTED"
    SYMBOL_INFO_ERROR = "MT5_SYMBOL_INFO_ERROR"
    TICK_ERROR = "MT5_TICK_ERROR"
    CANDLE_DATA_ERROR = "MT5_CANDLE_DATA_ERROR"
    POSITION_DATA_ERROR = "MT5_POSITION_DATA_ERROR"
    DATA_MAPPING_ERROR = "MT5_DATA_MAPPING_ERROR"
    INVALID_REQUEST = "MT5_INVALID_REQUEST"


class MT5ClientError(RuntimeError):
    """Sanitized exception raised for all adapter failures."""

    def __init__(
        self,
        category: MT5ErrorCategory,
        operation: str,
        message: str,
        *,
        vendor_code: int | None = None,
    ) -> None:
        self.category = category
        self.operation = operation
        self.vendor_code = vendor_code
        self.safe_message = message
        code_suffix = "" if vendor_code is None else f"; vendor_code={vendor_code}"
        super().__init__(f"{category.value}: {message}; operation={operation}{code_suffix}")
