"""Public read-only MetaTrader 5 client."""

import logging
from collections.abc import Callable
from threading import RLock

from ai_trading_team.config.settings import MT5Settings
from ai_trading_team.mt5.backend import MetaTrader5Backend
from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.mt5.mappers import (
    map_account_info,
    map_candle,
    map_position,
    map_symbol_info,
    map_symbol_summary,
    map_terminal_health,
    map_tick,
    records,
)
from ai_trading_team.mt5.protocols import MT5ReadBackend
from ai_trading_team.schemas.common import Symbol
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5Candle,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5SymbolSummary,
    MT5TerminalHealth,
    MT5Tick,
)
from ai_trading_team.utils.logging import get_logger
from ai_trading_team.utils.time import utc_now

MAX_CANDLE_COUNT = 5_000


class MT5ReadOnlyClient:
    """Own the MT5 lifecycle and expose only approved read operations."""

    def __init__(
        self,
        settings: MT5Settings,
        *,
        backend: MT5ReadBackend | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._logger = logger or get_logger(__name__)
        self._initialized = False
        self._lock = RLock()

    def initialize(self) -> MT5TerminalHealth:
        """Connect and optionally authenticate using the injected immutable settings."""
        with self._lock:
            if self._initialized:
                return self.health_check()

            backend = self._backend or MetaTrader5Backend.load()
            self._backend = backend
            terminal_path = (
                str(self._settings.terminal_path)
                if self._settings.terminal_path is not None
                else None
            )
            try:
                initialized = backend.initialize(
                    terminal_path,
                    self._settings.timeout_ms,
                    self._settings.portable,
                )
            except MT5ClientError:
                raise
            except Exception as exc:
                raise self._failure(
                    MT5ErrorCategory.INITIALIZATION_ERROR,
                    "initialize",
                    "MetaTrader 5 initialization raised an unexpected error",
                ) from exc
            if not initialized:
                raise self._failure(
                    MT5ErrorCategory.INITIALIZATION_ERROR,
                    "initialize",
                    "MetaTrader 5 initialization failed",
                )

            self._initialized = True
            try:
                if self._settings.has_explicit_credentials:
                    self._authenticate()
                health = self.health_check()
            except Exception:
                if self._initialized:
                    self._safe_shutdown_after_failed_startup()
                raise

            self._logger.info("mt5_initialized", extra={"operation": "initialize"})
            return health

    def health_check(self) -> MT5TerminalHealth:
        """Return sanitized terminal and authentication health."""
        with self._lock:
            backend = self._require_initialized("health_check")
            terminal_raw = self._read(
                "health_check",
                MT5ErrorCategory.TERMINAL_UNAVAILABLE,
                backend.terminal_info,
            )
            if terminal_raw is None:
                raise self._failure(
                    MT5ErrorCategory.TERMINAL_UNAVAILABLE,
                    "health_check",
                    "terminal information is unavailable",
                )
            account_raw = self._read(
                "health_check",
                MT5ErrorCategory.ACCOUNT_INFO_ERROR,
                backend.account_info,
            )
            terminal_version = self._read(
                "health_check",
                MT5ErrorCategory.TERMINAL_UNAVAILABLE,
                backend.version,
            )
            health = map_terminal_health(
                terminal_raw,
                account_raw,
                terminal_version,
                backend.package_version,
                utc_now(),
            )
            self._logger.info(
                "mt5_health_checked",
                extra={
                    "operation": "health_check",
                    "connection_state": health.connection_state.value,
                    "authenticated": health.authenticated,
                },
            )
            return health

    def get_account_info(self) -> MT5AccountInfo:
        """Return typed account and margin data."""
        with self._lock:
            backend = self._require_initialized("get_account_info")
            raw = self._read(
                "get_account_info",
                MT5ErrorCategory.ACCOUNT_INFO_ERROR,
                backend.account_info,
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.ACCOUNT_INFO_ERROR,
                    "get_account_info",
                    "account information is unavailable",
                )
            result = map_account_info(raw, utc_now())
            self._logger.info("mt5_account_info_read", extra={"operation": "get_account_info"})
            return result

    def get_symbols(self, pattern: str | None = None) -> tuple[MT5SymbolSummary, ...]:
        """Discover symbols, optionally using an MT5 group filter such as ``*,!*USD*``."""
        with self._lock:
            backend = self._require_initialized("get_symbols")
            normalized_pattern = self._validate_pattern(pattern)
            raw = self._read(
                "get_symbols",
                MT5ErrorCategory.SYMBOL_INFO_ERROR,
                lambda: backend.symbols_get(normalized_pattern),
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.SYMBOL_INFO_ERROR,
                    "get_symbols",
                    "symbol discovery failed",
                )
            retrieved_at = utc_now()
            result = tuple(
                map_symbol_summary(item, retrieved_at) for item in records(raw, "get_symbols")
            )
            self._logger.info(
                "mt5_symbols_read",
                extra={"operation": "get_symbols", "result_count": len(result)},
            )
            return result

    def get_symbol_info(self, symbol: Symbol) -> MT5SymbolInfo:
        """Return broker metadata without changing Market Watch selection state."""
        with self._lock:
            symbol = self._validate_symbol(symbol, "get_symbol_info")
            backend = self._require_initialized("get_symbol_info")
            raw = self._read(
                "get_symbol_info",
                MT5ErrorCategory.SYMBOL_INFO_ERROR,
                lambda: backend.symbol_info(symbol),
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.SYMBOL_UNAVAILABLE,
                    "get_symbol_info",
                    "requested symbol is unavailable",
                )
            result = map_symbol_info(raw, utc_now())
            self._logger.info(
                "mt5_symbol_info_read",
                extra={"operation": "get_symbol_info", "symbol": result.symbol},
            )
            return result

    def get_tick(self, symbol: Symbol) -> MT5Tick:
        """Return the current tick for an already selected symbol."""
        with self._lock:
            symbol = self._validate_symbol(symbol, "get_tick")
            backend = self._require_initialized("get_tick")
            self._require_selected_symbol(symbol)
            raw = self._read(
                "get_tick",
                MT5ErrorCategory.TICK_ERROR,
                lambda: backend.symbol_info_tick(symbol),
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.TICK_ERROR,
                    "get_tick",
                    "current tick is unavailable",
                )
            result = map_tick(raw, symbol, utc_now())
            self._logger.info(
                "mt5_tick_read",
                extra={"operation": "get_tick", "symbol": result.symbol},
            )
            return result

    def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        count: int,
        include_incomplete: bool = False,
    ) -> tuple[MT5Candle, ...]:
        """Read M15/H1/H4 bars, excluding the current incomplete bar by default."""
        with self._lock:
            symbol = self._validate_symbol(symbol, "get_candles")
            self._validate_candle_count(count)
            backend = self._require_initialized("get_candles")
            self._require_selected_symbol(symbol)
            start_position = 0 if include_incomplete else 1
            raw = self._read(
                "get_candles",
                MT5ErrorCategory.CANDLE_DATA_ERROR,
                lambda: backend.copy_rates_from_pos(
                    symbol,
                    timeframe,
                    start_position,
                    count,
                ),
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.CANDLE_DATA_ERROR,
                    "get_candles",
                    "candle data is unavailable",
                )
            retrieved_at = utc_now()
            result = tuple(
                sorted(
                    (
                        map_candle(item, symbol, timeframe, retrieved_at)
                        for item in records(raw, "get_candles")
                    ),
                    key=lambda candle: candle.open_time,
                )
            )
            if not result:
                raise self._failure(
                    MT5ErrorCategory.CANDLE_DATA_ERROR,
                    "get_candles",
                    "no candles were returned",
                )
            self._logger.info(
                "mt5_candles_read",
                extra={
                    "operation": "get_candles",
                    "symbol": symbol,
                    "timeframe": timeframe.value,
                    "result_count": len(result),
                    "include_incomplete": include_incomplete,
                },
            )
            return result

    def get_positions(self, symbol: Symbol | None = None) -> tuple[MT5OpenPosition, ...]:
        """Return existing open positions, optionally filtered by exact symbol."""
        with self._lock:
            if symbol is not None:
                symbol = self._validate_symbol(symbol, "get_positions")
            backend = self._require_initialized("get_positions")
            raw = self._read(
                "get_positions",
                MT5ErrorCategory.POSITION_DATA_ERROR,
                lambda: backend.positions_get(symbol),
            )
            if raw is None:
                raise self._failure(
                    MT5ErrorCategory.POSITION_DATA_ERROR,
                    "get_positions",
                    "open-position data is unavailable",
                )
            retrieved_at = utc_now()
            result = tuple(
                map_position(item, retrieved_at) for item in records(raw, "get_positions")
            )
            self._logger.info(
                "mt5_positions_read",
                extra={"operation": "get_positions", "result_count": len(result)},
            )
            return result

    def shutdown(self) -> None:
        """Close the Python terminal connection without altering broker positions."""
        with self._lock:
            backend = self._backend
            try:
                if backend is not None and self._initialized:
                    backend.shutdown()
            except Exception as exc:
                raise MT5ClientError(
                    MT5ErrorCategory.TERMINAL_UNAVAILABLE,
                    "shutdown",
                    "MetaTrader 5 shutdown raised an unexpected error",
                ) from exc
            finally:
                self._initialized = False
            self._logger.info("mt5_shutdown", extra={"operation": "shutdown"})

    def _authenticate(self) -> None:
        backend = self._require_initialized("authenticate")
        login = self._settings.login
        password = self._settings.password
        server = self._settings.server
        if login is None or password is None or server is None:
            raise MT5ClientError(
                MT5ErrorCategory.AUTHENTICATION_ERROR,
                "authenticate",
                "explicit MT5 credentials are incomplete",
            )
        try:
            authenticated = backend.login(
                login,
                password.get_secret_value(),
                server,
                self._settings.timeout_ms,
            )
        except Exception as exc:
            error = self._failure(
                MT5ErrorCategory.AUTHENTICATION_ERROR,
                "authenticate",
                "MetaTrader 5 authentication raised an unexpected error",
            )
            self._safe_shutdown_after_failed_startup()
            raise error from exc
        if not authenticated:
            error = self._failure(
                MT5ErrorCategory.AUTHENTICATION_ERROR,
                "authenticate",
                "MetaTrader 5 authentication failed",
            )
            self._safe_shutdown_after_failed_startup()
            raise error
        self._logger.info("mt5_authenticated", extra={"operation": "authenticate"})

    def _safe_shutdown_after_failed_startup(self) -> None:
        backend = self._backend
        try:
            if backend is not None:
                backend.shutdown()
        except Exception:
            self._logger.error(
                "mt5_shutdown_after_failed_startup_failed",
                extra={"operation": "shutdown"},
            )
        finally:
            self._initialized = False

    def _require_initialized(self, operation: str) -> MT5ReadBackend:
        if not self._initialized or self._backend is None:
            raise MT5ClientError(
                MT5ErrorCategory.NOT_INITIALIZED,
                operation,
                "MetaTrader 5 client is not initialized",
            )
        return self._backend

    def _require_selected_symbol(self, symbol: Symbol) -> None:
        info = self.get_symbol_info(symbol)
        if not info.selected:
            raise MT5ClientError(
                MT5ErrorCategory.SYMBOL_NOT_SELECTED,
                "validate_symbol",
                "requested symbol is not selected for terminal reads",
            )

    def _failure(
        self,
        category: MT5ErrorCategory,
        operation: str,
        message: str,
    ) -> MT5ClientError:
        vendor_code: int | None = None
        if self._backend is not None:
            try:
                vendor_code, _vendor_message = self._backend.last_error()
            except Exception:
                vendor_code = None
        self._logger.error(
            "mt5_operation_failed",
            extra={
                "operation": operation,
                "error_category": category.value,
                "vendor_code": vendor_code,
            },
        )
        return MT5ClientError(category, operation, message, vendor_code=vendor_code)

    def _read(
        self,
        operation: str,
        category: MT5ErrorCategory,
        function: Callable[[], object | None],
    ) -> object | None:
        try:
            return function()
        except MT5ClientError:
            raise
        except Exception as exc:
            raise self._failure(
                category,
                operation,
                "MetaTrader 5 read raised an unexpected error",
            ) from exc

    @staticmethod
    def _validate_pattern(pattern: str | None) -> str | None:
        if pattern is None:
            return None
        normalized = pattern.strip()
        if not normalized or len(normalized) > 255:
            raise MT5ClientError(
                MT5ErrorCategory.INVALID_REQUEST,
                "get_symbols",
                "symbol pattern must contain 1 to 255 characters",
            )
        return normalized

    @staticmethod
    def _validate_candle_count(count: int) -> None:
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or count > MAX_CANDLE_COUNT
        ):
            raise MT5ClientError(
                MT5ErrorCategory.INVALID_REQUEST,
                "get_candles",
                f"count must be between 1 and {MAX_CANDLE_COUNT}",
            )

    @staticmethod
    def _validate_symbol(symbol: str, operation: str) -> str:
        normalized = symbol.strip()
        if not normalized or len(normalized) > 64:
            raise MT5ClientError(
                MT5ErrorCategory.INVALID_REQUEST,
                operation,
                "symbol must contain 1 to 64 characters",
            )
        return normalized
