"""Vendor backend restricted to one protected market-order operation."""

from typing import Protocol

from ai_trading_team.mt5.backend import MetaTrader5Backend


class MT5DemoBackend(Protocol):
    """Internal vendor boundary; it is never exposed to agents or orchestration."""

    @property
    def package_version(self) -> str: ...

    def constant(self, name: str) -> int: ...

    def terminal_info(self) -> object | None: ...

    def account_info(self) -> object | None: ...

    def version(self) -> object | None: ...

    def symbol_info(self, symbol: str) -> object | None: ...

    def symbol_info_tick(self, symbol: str) -> object | None: ...

    def positions_get(self, symbol: str | None) -> object | None: ...

    def order_check_request(self, request: dict[str, object]) -> object | None: ...

    def submit_protected_market_request(self, request: dict[str, object]) -> object | None: ...

    def shutdown(self) -> None: ...


class MetaTrader5DemoBackend(MetaTrader5Backend):
    """The only concrete production wrapper that can reach the vendor mutation API."""

    def constant(self, name: str) -> int:
        value = getattr(self._module, name, None)
        if not isinstance(value, int):
            raise RuntimeError("required MetaTrader5 constant is unavailable")
        return value

    def order_check_request(self, request: dict[str, object]) -> object | None:
        return self._callable("order_check")(request)

    def submit_protected_market_request(self, request: dict[str, object]) -> object | None:
        return self._callable("order_send")(request)
