"""Canonical historical dataset and replay serialization tests."""

from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.replay import REPLAY_CUTOFF, replay_build, replay_dataset

from ai_trading_team.replay.serialization import (
    canonical_replay_bytes,
    content_digest,
    dataset_digest,
)
from ai_trading_team.replay.source import FileHistoricalMarketDataSource
from ai_trading_team.schemas.replay import OutcomeHorizon, ReplayFrame


def test_dataset_digest_is_stable_and_covers_candle_values() -> None:
    dataset = replay_dataset()
    assert dataset_digest(dataset) == dataset.dataset_digest
    candle = dataset.candles[0].model_copy(update={"close": Decimal("1.99999")})
    changed = dataset.model_copy(update={"candles": (candle, *dataset.candles[1:])})
    assert dataset_digest(changed) != dataset.dataset_digest


def test_canonical_replay_bytes_normalize_decimal_and_utc() -> None:
    payload = {
        "price": Decimal("1.2300"),
        "timestamp": REPLAY_CUTOFF.astimezone(timezone(timedelta(hours=7))),
    }
    assert canonical_replay_bytes(payload) == (
        b'{"price":"1.23","timestamp":"2026-09-10T12:00:00.000000Z"}'
    )


def test_file_source_loads_local_utf8_json_without_network(tmp_path) -> None:  # type: ignore[no-untyped-def]
    dataset = replay_dataset()
    path = tmp_path / "dataset.json"
    path.write_text(dataset.model_dump_json(), encoding="utf-8")
    source = FileHistoricalMarketDataSource(path)
    assert source.dataset_digest == dataset.dataset_digest


def test_horizon_requires_exactly_one_finite_bound() -> None:
    with pytest.raises(ValidationError):
        OutcomeHorizon(max_bars=None, max_elapsed=None)
    with pytest.raises(ValidationError):
        OutcomeHorizon(max_bars=1, max_elapsed=timedelta(hours=1))


def test_replay_frame_rejects_embedded_outcome_fields() -> None:
    frame = replay_build()[3].frame
    payload = frame.model_dump()
    payload["future_outcome"] = "TAKE_PROFIT_REACHED"
    with pytest.raises(ValidationError):
        ReplayFrame.model_validate(payload)


def test_content_digest_and_canonical_bytes_repeat() -> None:
    result = replay_build()[3]
    assert content_digest(result) == content_digest(result.model_copy())
    assert canonical_replay_bytes(result) == canonical_replay_bytes(result.model_copy())
