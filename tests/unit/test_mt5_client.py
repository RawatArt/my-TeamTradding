import io
from datetime import UTC
from decimal import Decimal

import pytest
from pydantic import SecretStr
from tests.fakes.mt5 import FakeMT5Backend, symbol_record

from ai_trading_team.config.settings import MT5Settings
from ai_trading_team.mt5.client import MAX_CANDLE_COUNT, MT5ReadOnlyClient
from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    BrokerPositionSide,
    MT5ConnectionState,
    SymbolTradeMode,
    Timeframe,
)
from ai_trading_team.utils.logging import configure_logging


def initialized_client(
    backend: FakeMT5Backend,
    settings: MT5Settings | None = None,
) -> MT5ReadOnlyClient:
    client = MT5ReadOnlyClient(settings or MT5Settings(), backend=backend)
    client.initialize()
    return client


def test_initialize_without_explicit_credentials_uses_current_terminal_session() -> None:
    backend = FakeMT5Backend()
    client = MT5ReadOnlyClient(MT5Settings(), backend=backend)

    health = client.initialize()

    assert health.connection_state is MT5ConnectionState.CONNECTED
    assert health.authenticated is True
    assert health.package_version == "5.0.6180"
    assert backend.initialize_calls == [(None, 60_000, False)]
    assert backend.login_calls == []


def test_initialize_authenticates_when_complete_credentials_are_configured() -> None:
    backend = FakeMT5Backend()
    settings = MT5Settings(
        login=12345678,
        password=SecretStr("demo-password"),
        server="Broker-Demo",
    )

    initialized_client(backend, settings)

    assert backend.login_calls == [(12345678, "demo-password", "Broker-Demo", 60_000)]


def test_failed_initialization_raises_typed_sanitized_error() -> None:
    backend = FakeMT5Backend()
    backend.initialize_result = False
    backend.last_error_result = (-10003, "sensitive vendor details")
    client = MT5ReadOnlyClient(MT5Settings(), backend=backend)

    with pytest.raises(MT5ClientError) as caught:
        client.initialize()

    assert caught.value.category is MT5ErrorCategory.INITIALIZATION_ERROR
    assert caught.value.vendor_code == -10003
    assert "sensitive vendor details" not in str(caught.value)


def test_failed_authentication_shuts_down_and_never_logs_credentials() -> None:
    stream = io.StringIO()
    logger = configure_logging(stream=stream)
    backend = FakeMT5Backend()
    backend.login_result = False
    backend.last_error_result = (-6, "login 12345678 at Broker-Demo failed")
    client = MT5ReadOnlyClient(
        MT5Settings(
            login=12345678,
            password=SecretStr("demo-password"),
            server="Broker-Demo",
        ),
        backend=backend,
        logger=logger,
    )

    with pytest.raises(MT5ClientError) as caught:
        client.initialize()

    assert caught.value.category is MT5ErrorCategory.AUTHENTICATION_ERROR
    assert backend.shutdown_calls == 1
    output = stream.getvalue()
    assert "12345678" not in output
    assert "demo-password" not in output
    assert "Broker-Demo" not in output


def test_read_before_initialize_is_rejected() -> None:
    client = MT5ReadOnlyClient(MT5Settings(), backend=FakeMT5Backend())

    with pytest.raises(MT5ClientError) as caught:
        client.get_account_info()

    assert caught.value.category is MT5ErrorCategory.NOT_INITIALIZED


def test_initialize_closes_connection_when_health_validation_fails() -> None:
    backend = FakeMT5Backend()
    backend.terminal_info_result = None
    client = MT5ReadOnlyClient(MT5Settings(), backend=backend)

    with pytest.raises(MT5ClientError) as caught:
        client.initialize()

    assert caught.value.category is MT5ErrorCategory.TERMINAL_UNAVAILABLE
    assert backend.shutdown_calls == 1


def test_account_info_maps_balance_equity_and_margin_as_decimals() -> None:
    account = initialized_client(FakeMT5Backend()).get_account_info()

    assert account.trade_mode is BrokerAccountMode.DEMO
    assert account.balance == Decimal("50.0")
    assert account.equity == Decimal("49.9")
    assert account.margin == Decimal("1.25")
    assert account.margin_free == Decimal("48.65")
    assert account.margin_level == Decimal("3992.0")
    assert all(
        isinstance(value, Decimal)
        for value in (account.balance, account.equity, account.margin, account.margin_free)
    )


def test_get_symbols_passes_normalized_optional_filter() -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    symbols = client.get_symbols("  *USD*,!*JPY*  ")

    assert backend.symbol_pattern_calls == ["*USD*,!*JPY*"]
    assert symbols[0].symbol == "EURUSD.a"
    assert symbols[0].selected is True


def test_get_symbols_none_explicitly_requests_all_broker_symbols() -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    client.get_symbols()

    assert backend.symbol_pattern_calls == [None]


@pytest.mark.parametrize("pattern", ["", "   ", "x" * 256])
def test_get_symbols_rejects_invalid_filter(pattern: str) -> None:
    client = initialized_client(FakeMT5Backend())

    with pytest.raises(MT5ClientError) as caught:
        client.get_symbols(pattern)

    assert caught.value.category is MT5ErrorCategory.INVALID_REQUEST


def test_symbol_info_contains_required_broker_metadata() -> None:
    info = initialized_client(FakeMT5Backend()).get_symbol_info("EURUSD.a")

    assert info.digits == 5
    assert info.point == Decimal("0.00001")
    assert info.trade_tick_size == Decimal("0.00001")
    assert info.trade_tick_value == Decimal("1.0")
    assert info.trade_contract_size == Decimal("100000.0")
    assert info.volume_min == Decimal("0.01")
    assert info.volume_max == Decimal("100.0")
    assert info.volume_step == Decimal("0.01")
    assert info.trade_stops_level == 20
    assert info.trade_freeze_level == 10
    assert info.currency_base == "EUR"
    assert info.currency_profit == "USD"
    assert info.trading_mode is SymbolTradeMode.FULL


@pytest.mark.parametrize("symbol", ["", "   ", "x" * 65])
def test_symbol_reads_reject_invalid_symbol_names(symbol: str) -> None:
    client = initialized_client(FakeMT5Backend())

    with pytest.raises(MT5ClientError) as caught:
        client.get_symbol_info(symbol)

    assert caught.value.category is MT5ErrorCategory.INVALID_REQUEST


def test_tick_requires_symbol_to_already_be_selected() -> None:
    backend = FakeMT5Backend()
    backend.symbol_info_result = symbol_record(selected=False)
    client = initialized_client(backend)

    with pytest.raises(MT5ClientError) as caught:
        client.get_tick("EURUSD.a")

    assert caught.value.category is MT5ErrorCategory.SYMBOL_NOT_SELECTED
    assert backend.tick_calls == []


def test_tick_is_typed_decimal_and_utc_without_returning_raw_vendor_data() -> None:
    tick = initialized_client(FakeMT5Backend()).get_tick("EURUSD.a")

    assert tick.bid == Decimal("1.08123")
    assert tick.ask == Decimal("1.08135")
    assert tick.spread == Decimal("0.00012")
    assert isinstance(tick.bid, Decimal)
    assert tick.source_time.tzinfo is UTC
    assert tick.source_time.microsecond == 123_000
    assert type(tick).__module__ == "ai_trading_team.schemas.mt5"


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_candles_support_each_approved_timeframe_and_exclude_current_by_default(
    timeframe: Timeframe,
) -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    candles = client.get_candles("EURUSD.a", timeframe, 2)

    assert backend.candle_calls[-1] == ("EURUSD.a", timeframe, 1, 2)
    assert len(candles) == 2
    assert candles[0].open_time < candles[1].open_time
    assert candles[0].timeframe is timeframe
    assert isinstance(candles[0].open, Decimal)
    assert candles[0].open_time.tzinfo is UTC


def test_candles_can_include_current_bar_only_when_explicitly_requested() -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    client.get_candles("EURUSD.a", Timeframe.M15, 1, include_incomplete=True)

    assert backend.candle_calls[-1] == ("EURUSD.a", Timeframe.M15, 0, 1)


@pytest.mark.parametrize("count", [0, -1, MAX_CANDLE_COUNT + 1, True])
def test_candle_count_outside_safe_bounds_is_rejected(count: int) -> None:
    client = initialized_client(FakeMT5Backend())

    with pytest.raises(MT5ClientError) as caught:
        client.get_candles("EURUSD.a", Timeframe.M15, count)

    assert caught.value.category is MT5ErrorCategory.INVALID_REQUEST


def test_empty_candle_result_is_an_error_not_valid_market_data() -> None:
    backend = FakeMT5Backend()
    backend.candles_result = ()
    client = initialized_client(backend)

    with pytest.raises(MT5ClientError) as caught:
        client.get_candles("EURUSD.a", Timeframe.M15, 10)

    assert caught.value.category is MT5ErrorCategory.CANDLE_DATA_ERROR


def test_positions_map_to_typed_existing_position_records() -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    positions = client.get_positions("EURUSD.a")

    assert backend.position_calls == ["EURUSD.a"]
    assert positions[0].side is BrokerPositionSide.BUY
    assert positions[0].volume == Decimal("0.01")
    assert positions[0].open_time.tzinfo is UTC


def test_empty_positions_are_valid_but_none_is_a_typed_failure() -> None:
    backend = FakeMT5Backend()
    backend.positions_result = ()
    client = initialized_client(backend)
    assert client.get_positions() == ()

    backend.positions_result = None
    with pytest.raises(MT5ClientError) as caught:
        client.get_positions()

    assert caught.value.category is MT5ErrorCategory.POSITION_DATA_ERROR


def test_shutdown_is_idempotent() -> None:
    backend = FakeMT5Backend()
    client = initialized_client(backend)

    client.shutdown()
    client.shutdown()

    assert backend.shutdown_calls == 1
