from datetime import UTC, datetime, timedelta, timezone

import pytest

from ai_trading_team.utils.time import normalize_utc, utc_now


def test_utc_now_returns_aware_utc_datetime() -> None:
    value = utc_now()

    assert value.tzinfo is UTC
    assert value.utcoffset() == timedelta(0)


def test_normalize_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(datetime(2026, 9, 10))


def test_normalize_utc_converts_aware_datetime() -> None:
    value = datetime(2026, 9, 10, 7, tzinfo=timezone(timedelta(hours=7)))

    assert normalize_utc(value) == datetime(2026, 9, 10, tzinfo=UTC)

