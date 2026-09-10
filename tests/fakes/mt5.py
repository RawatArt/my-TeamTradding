"""Controllable fake for the narrow M1 MetaTrader backend protocol."""

from typing import Final

from ai_trading_team.schemas.enums import Timeframe

EPOCH_SECONDS: Final = 1_757_462_400
EPOCH_MILLISECONDS: Final = EPOCH_SECONDS * 1_000 + 123


def account_record() -> dict[str, object]:
    return {
        "login": 12345678,
        "trade_mode": 0,
        "leverage": 100,
        "limit_orders": 200,
        "margin_so_mode": 0,
        "trade_allowed": True,
        "trade_expert": True,
        "margin_mode": 2,
        "currency_digits": 2,
        "fifo_close": False,
        "balance": 50.0,
        "credit": 0.0,
        "profit": -0.1,
        "equity": 49.9,
        "margin": 1.25,
        "margin_free": 48.65,
        "margin_level": 3992.0,
        "margin_so_call": 50.0,
        "margin_so_so": 30.0,
        "margin_initial": 0.0,
        "margin_maintenance": 0.0,
        "assets": 0.0,
        "liabilities": 0.0,
        "commission_blocked": 0.0,
        "server": "Broker-Demo",
        "currency": "USD",
        "company": "Broker",
    }


def symbol_record(*, selected: bool = True, name: str = "EURUSD.a") -> dict[str, object]:
    return {
        "name": name,
        "description": "Euro vs US Dollar",
        "path": "Forex\\Majors",
        "select": selected,
        "visible": selected,
        "digits": 5,
        "point": 0.00001,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "trade_contract_size": 100000.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_stops_level": 20,
        "trade_freeze_level": 10,
        "currency_base": "EUR",
        "currency_profit": "USD",
        "trade_mode": 4,
    }


def tick_record() -> dict[str, object]:
    return {
        "time": EPOCH_SECONDS,
        "time_msc": EPOCH_MILLISECONDS,
        "bid": 1.08123,
        "ask": 1.08135,
        "last": 1.0813,
        "volume": 3,
        "volume_real": 3.5,
        "flags": 6,
    }


def candle_record(*, timestamp: int = EPOCH_SECONDS) -> dict[str, object]:
    return {
        "time": timestamp,
        "open": 1.08,
        "high": 1.09,
        "low": 1.07,
        "close": 1.085,
        "tick_volume": 123,
        "spread": 12,
        "real_volume": 5,
    }


def position_record() -> dict[str, object]:
    return {
        "ticket": 101,
        "time": EPOCH_SECONDS,
        "time_msc": EPOCH_MILLISECONDS,
        "time_update": EPOCH_SECONDS + 5,
        "time_update_msc": EPOCH_MILLISECONDS + 5_000,
        "type": 0,
        "magic": 0,
        "identifier": 201,
        "reason": 0,
        "volume": 0.01,
        "price_open": 1.08,
        "sl": 1.07,
        "tp": 1.1,
        "price_current": 1.085,
        "swap": -0.01,
        "profit": 0.05,
        "symbol": "EURUSD.a",
        "comment": "manual demo position",
        "external_id": "",
    }


class FakeMT5Backend:
    """Fake whose methods exactly match MT5ReadBackend."""

    package_version = "5.0.6180"

    def __init__(self) -> None:
        self.initialize_result = True
        self.login_result = True
        self.last_error_result: tuple[int | None, str] = (0, "success")
        self.version_result: object | None = (500, 6180, "05 Sep 2026")
        self.terminal_info_result: object | None = {
            "connected": True,
            "build": 5000,
            "name": "MetaTrader 5",
            "company": "MetaQuotes",
            "tradeapi_disabled": False,
        }
        self.account_info_result: object | None = account_record()
        self.symbols_result: object | None = (symbol_record(),)
        self.symbol_info_result: object | None = symbol_record()
        self.tick_result: object | None = tick_record()
        self.candles_result: object | None = (
            candle_record(timestamp=EPOCH_SECONDS),
            candle_record(timestamp=EPOCH_SECONDS - 900),
        )
        self.positions_result: object | None = (position_record(),)
        self.initialize_calls: list[tuple[str | None, int, bool]] = []
        self.login_calls: list[tuple[int, str, str, int]] = []
        self.symbol_pattern_calls: list[str | None] = []
        self.symbol_info_calls: list[str] = []
        self.tick_calls: list[str] = []
        self.candle_calls: list[tuple[str, Timeframe, int, int]] = []
        self.position_calls: list[str | None] = []
        self.shutdown_calls = 0

    def initialize(self, path: str | None, timeout_ms: int, portable: bool) -> bool:
        self.initialize_calls.append((path, timeout_ms, portable))
        return self.initialize_result

    def login(self, login: int, password: str, server: str, timeout_ms: int) -> bool:
        self.login_calls.append((login, password, server, timeout_ms))
        return self.login_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def last_error(self) -> tuple[int | None, str]:
        return self.last_error_result

    def version(self) -> object | None:
        return self.version_result

    def terminal_info(self) -> object | None:
        return self.terminal_info_result

    def account_info(self) -> object | None:
        return self.account_info_result

    def symbols_get(self, pattern: str | None) -> object | None:
        self.symbol_pattern_calls.append(pattern)
        return self.symbols_result

    def symbol_info(self, symbol: str) -> object | None:
        self.symbol_info_calls.append(symbol)
        return self.symbol_info_result

    def symbol_info_tick(self, symbol: str) -> object | None:
        self.tick_calls.append(symbol)
        return self.tick_result

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: Timeframe,
        start_position: int,
        count: int,
    ) -> object | None:
        self.candle_calls.append((symbol, timeframe, start_position, count))
        return self.candles_result

    def positions_get(self, symbol: str | None) -> object | None:
        self.position_calls.append(symbol)
        return self.positions_result
