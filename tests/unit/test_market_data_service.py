from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from tests.fakes.market import (
    SNAPSHOT_END,
    SNAPSHOT_START,
    SYMBOL,
    FakeMarketDataSource,
    SequenceClock,
    account_info,
    candles,
    position,
    tick,
)

from ai_trading_team.config import MarketDataSettings
from ai_trading_team.market import MarketDataError, MarketDataErrorCategory, MarketDataService
from ai_trading_team.mt5 import MT5ClientError, MT5ErrorCategory
from ai_trading_team.schemas.enums import (
    DataValidityState,
    FreshnessState,
    SnapshotWarningCode,
    Timeframe,
)
from ai_trading_team.schemas.mt5 import MT5SymbolInfo


def service(
    source: FakeMarketDataSource,
    *,
    symbol: str | None = SYMBOL,
    settings: MarketDataSettings | None = None,
    end: datetime = SNAPSHOT_END,
) -> MarketDataService:
    return MarketDataService(
        source,
        settings
        or MarketDataSettings(
            m15_candle_count=2,
            h1_candle_count=2,
            h4_candle_count=2,
        ),
        symbol,
        clock=SequenceClock(
            SNAPSHOT_START,
            SNAPSHOT_START + timedelta(seconds=3),
            end,
        ),
    )


def test_builds_one_immutable_cycle_and_snapshot_traceable_aggregate() -> None:
    source = FakeMarketDataSource()

    snapshot = service(source).build_snapshot("cycle-001", "snapshot-analysis-001", Timeframe.M15)

    assert snapshot.cycle_id == "cycle-001"
    assert snapshot.snapshot_id == "snapshot-analysis-001"
    assert snapshot.symbol == SYMBOL
    assert snapshot.primary_timeframe is Timeframe.M15
    assert snapshot.consistency.validity is DataValidityState.VALID
    assert snapshot.consistency.freshness.overall is FreshnessState.FRESH
    assert snapshot.spread == Decimal("0.00012")
    assert source.position_calls == [SYMBOL]
    assert source.candle_calls == [
        (SYMBOL, Timeframe.M15, 2, False),
        (SYMBOL, Timeframe.H1, 2, False),
        (SYMBOL, Timeframe.H4, 2, False),
    ]
    with pytest.raises(Exception, match="frozen"):
        snapshot.symbol = "changed"


def test_stale_but_valid_observations_produce_a_snapshot_with_warnings() -> None:
    source = FakeMarketDataSource()
    end = SNAPSHOT_START + timedelta(seconds=40)
    source.account_result = account_info(retrieved_at=SNAPSHOT_START + timedelta(seconds=1))
    source.tick_result = tick(source_time=SNAPSHOT_START - timedelta(hours=1))
    source.candle_results = {
        timeframe: candles(
            timeframe,
            latest_close=SNAPSHOT_START - timedelta(days=2),
        )
        for timeframe in Timeframe
    }

    snapshot = service(source, end=end).build_snapshot(
        "cycle-stale", "snapshot-stale", Timeframe.H1
    )

    assert snapshot.consistency.validity is DataValidityState.VALID
    assert snapshot.consistency.freshness.overall is FreshnessState.STALE
    assert snapshot.consistency.freshness.tick.state is FreshnessState.STALE
    assert {warning.code for warning in snapshot.consistency.validation_warnings} >= {
        SnapshotWarningCode.STALE_TICK,
        SnapshotWarningCode.STALE_ACCOUNT,
        SnapshotWarningCode.STALE_CANDLE,
        SnapshotWarningCode.SLOW_SNAPSHOT,
    }


def test_positions_for_other_symbols_are_omitted_without_invalidating_snapshot() -> None:
    source = FakeMarketDataSource()
    source.positions_result = (
        position(symbol=SYMBOL, ticket=101),
        position(symbol="USDJPY.a", ticket=202),
    )

    snapshot = service(source).build_snapshot(
        "cycle-positions", "snapshot-positions", Timeframe.M15
    )

    assert [item.symbol for item in snapshot.open_positions] == [SYMBOL]
    warning = next(
        item
        for item in snapshot.consistency.validation_warnings
        if item.code is SnapshotWarningCode.OUT_OF_SCOPE_POSITION_OMITTED
    )
    assert warning.omitted_count == 1


def test_missing_configured_symbol_fails_before_reading_source() -> None:
    source = FakeMarketDataSource()

    with pytest.raises(MarketDataError) as raised:
        service(source, symbol=None).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.MISSING_SYMBOL
    assert source.symbol_info_calls == []


def test_invalid_identifier_format_fails_before_reading_source() -> None:
    source = FakeMarketDataSource()

    with pytest.raises(MarketDataError) as raised:
        service(source).build_snapshot("bad cycle id", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE
    assert source.symbol_info_calls == []


def test_fewer_candles_than_configured_is_an_explicit_error() -> None:
    source = FakeMarketDataSource()
    source.candle_results[Timeframe.M15] = candles(Timeframe.M15, count=1)

    with pytest.raises(MarketDataError) as raised:
        service(source).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.INSUFFICIENT_CANDLE_HISTORY
    assert raised.value.timeframe is Timeframe.M15


def test_incomplete_candle_is_rejected_as_inconsistent_timestamp() -> None:
    source = FakeMarketDataSource()
    source.candle_results[Timeframe.H1] = candles(
        Timeframe.H1,
        latest_close=SNAPSHOT_END + timedelta(minutes=1),
    )

    with pytest.raises(MarketDataError) as raised:
        service(source).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS


def test_future_tick_is_invalid_rather_than_stale() -> None:
    source = FakeMarketDataSource()
    source.tick_result = tick(source_time=SNAPSHOT_END + timedelta(seconds=1))

    with pytest.raises(MarketDataError) as raised:
        service(source).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.INCONSISTENT_TIMESTAMPS


def test_wrong_timeframe_in_collection_is_rejected() -> None:
    source = FakeMarketDataSource()
    source.candle_results[Timeframe.M15] = candles(Timeframe.H1)

    with pytest.raises(MarketDataError) as raised:
        service(source).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.INVALID_TIMEFRAME_DATA


def test_mt5_error_is_wrapped_without_vendor_message() -> None:
    class FailingSource(FakeMarketDataSource):
        def get_symbol_info(self, symbol: str) -> MT5SymbolInfo:
            raise MT5ClientError(
                MT5ErrorCategory.TICK_ERROR,
                "get_tick",
                "sanitized upstream failure",
                vendor_code=-1,
            )

    with pytest.raises(MarketDataError) as raised:
        service(FailingSource()).build_snapshot("cycle-001", "snapshot-001", Timeframe.M15)

    assert raised.value.category is MarketDataErrorCategory.SNAPSHOT_COMPOSITION_FAILURE
    assert raised.value.cause_category == MT5ErrorCategory.TICK_ERROR.value
    assert "vendor" not in raised.value.safe_message
