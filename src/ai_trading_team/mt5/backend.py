"""Narrow wrapper around the platform-specific MetaTrader5 module."""

from collections.abc import Callable
from importlib import import_module
from typing import cast

from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.schemas.enums import Timeframe


class MetaTrader5Backend:
    """Allowlisted access to vendor lifecycle and read operations."""

    def __init__(self, module: object) -> None:
        self._module = module

    @classmethod
    def load(cls) -> "MetaTrader5Backend":
        """Load the Windows-only dependency without making import mandatory for unit tests."""
        try:
            module = import_module("MetaTrader5")
        except (ImportError, OSError) as exc:
            raise MT5ClientError(
                MT5ErrorCategory.DEPENDENCY_UNAVAILABLE,
                "load_dependency",
                "MetaTrader5 5.0.6180 is unavailable on this interpreter/platform",
            ) from exc
        return cls(module)

    @property
    def package_version(self) -> str:
        return str(getattr(self._module, "__version__", "unknown"))

    def _callable(self, name: str) -> Callable[..., object]:
        value = getattr(self._module, name, None)
        if not callable(value):
            raise MT5ClientError(
                MT5ErrorCategory.DEPENDENCY_UNAVAILABLE,
                "load_dependency",
                f"MetaTrader5 does not provide required operation {name}",
            )
        return cast(Callable[..., object], value)

    def initialize(self, path: str | None, timeout_ms: int, portable: bool) -> bool:
        kwargs: dict[str, object] = {"timeout": timeout_ms, "portable": portable}
        result = (
            self._callable("initialize")(path, **kwargs)
            if path is not None
            else self._callable("initialize")(**kwargs)
        )
        return bool(result)

    def login(self, login: int, password: str, server: str, timeout_ms: int) -> bool:
        result = self._callable("login")(
            login,
            password=password,
            server=server,
            timeout=timeout_ms,
        )
        return bool(result)

    def shutdown(self) -> None:
        self._callable("shutdown")()

    def last_error(self) -> tuple[int | None, str]:
        result = self._callable("last_error")()
        if isinstance(result, tuple) and len(result) >= 2:
            code = result[0] if isinstance(result[0], int) else None
            return code, str(result[1])
        return None, "unavailable"

    def version(self) -> object | None:
        return self._callable("version")()

    def terminal_info(self) -> object | None:
        return self._callable("terminal_info")()

    def account_info(self) -> object | None:
        return self._callable("account_info")()

    def symbols_get(self, pattern: str | None) -> object | None:
        if pattern is None:
            return self._callable("symbols_get")()
        return self._callable("symbols_get")(group=pattern)

    def symbol_info(self, symbol: str) -> object | None:
        return self._callable("symbol_info")(symbol)

    def symbol_info_tick(self, symbol: str) -> object | None:
        return self._callable("symbol_info_tick")(symbol)

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_position: int,
        count: int,
    ) -> object | None:
        timeframe_name = {
            Timeframe.M15: "TIMEFRAME_M15",
            Timeframe.H1: "TIMEFRAME_H1",
            Timeframe.H4: "TIMEFRAME_H4",
        }[timeframe]
        timeframe_value = int(getattr(self._module, timeframe_name))
        return self._callable("copy_rates_from_pos")(
            symbol,
            timeframe_value,
            start_position,
            count,
        )

    def positions_get(self, symbol: str | None) -> object | None:
        if symbol is None:
            return self._callable("positions_get")()
        return self._callable("positions_get")(symbol=symbol)
