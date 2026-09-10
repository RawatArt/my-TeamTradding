from datetime import UTC, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.market import (
    SNAPSHOT_END,
    SNAPSHOT_START,
    SYMBOL,
    FakeMarketDataSource,
    SequenceClock,
)

from ai_trading_team.config import MarketDataSettings
from ai_trading_team.market import MarketDataService
from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.market import MarketSnapshot


def build_snapshot() -> MarketSnapshot:
    source = FakeMarketDataSource()
    return MarketDataService(
        source,
        MarketDataSettings(
            m15_candle_count=2,
            h1_candle_count=2,
            h4_candle_count=2,
        ),
        SYMBOL,
        clock=SequenceClock(
            SNAPSHOT_START,
            SNAPSHOT_START + timedelta(seconds=3),
            SNAPSHOT_END,
        ),
    ).build_snapshot("cycle-json", "snapshot-json", Timeframe.M15)


def test_snapshot_decimal_values_round_trip_as_decimal_not_float() -> None:
    snapshot = build_snapshot()

    payload = snapshot.model_dump_json()
    restored = MarketSnapshot.model_validate_json(payload)

    assert '"spread":"0.00012"' in payload
    assert isinstance(restored.spread, Decimal)
    assert isinstance(restored.tick.bid, Decimal)
    assert isinstance(restored.account.equity, Decimal)
    assert isinstance(restored.candles.h4[0].close, Decimal)
    assert isinstance(restored.open_positions[0].volume, Decimal)


def test_all_snapshot_boundary_timestamps_are_aware_utc() -> None:
    snapshot = build_snapshot()

    timestamps = (
        snapshot.snapshot_started_at,
        snapshot.snapshot_completed_at,
        snapshot.symbol_info.retrieved_at,
        snapshot.tick.source_time,
        snapshot.tick.retrieved_at,
        snapshot.account.retrieved_at,
        snapshot.consistency.source_timestamps.positions,
        snapshot.candles.m15[0].open_time,
        snapshot.open_positions[0].update_time,
    )

    assert all(item.tzinfo is UTC for item in timestamps)


def test_invalid_and_stale_are_distinct_snapshot_states() -> None:
    payload = build_snapshot().model_dump(mode="python")
    payload["consistency"]["validity"] = "INVALID"

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(payload)


def test_naive_snapshot_timestamp_is_rejected() -> None:
    payload = build_snapshot().model_dump(mode="python")
    payload["snapshot_started_at"] = SNAPSHOT_START.replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketSnapshot.model_validate(payload)


@pytest.mark.parametrize("field", ["cycle_id", "snapshot_id"])
def test_trace_identifiers_reject_invalid_format(field: str) -> None:
    payload = build_snapshot().model_dump(mode="python")
    payload[field] = "contains spaces"

    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(payload)


def test_multiple_snapshot_ids_can_be_retained_in_one_cycle() -> None:
    first = build_snapshot()
    payload = first.model_dump(mode="python")
    payload["snapshot_id"] = "snapshot-execution-validation"

    second = MarketSnapshot.model_validate(payload)

    assert second.cycle_id == first.cycle_id
    assert second.snapshot_id != first.snapshot_id
