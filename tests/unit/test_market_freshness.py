from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ai_trading_team.market.freshness import assess_freshness
from ai_trading_team.schemas.enums import FreshnessState


def test_freshness_boundary_is_inclusive() -> None:
    evaluated_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    result = assess_freshness(
        evaluated_at - timedelta(seconds=120), evaluated_at, timedelta(seconds=120)
    )

    assert result.state is FreshnessState.FRESH


def test_stale_is_a_valid_freshness_result() -> None:
    evaluated_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    result = assess_freshness(
        evaluated_at - timedelta(seconds=121), evaluated_at, timedelta(seconds=120)
    )

    assert result.state is FreshnessState.STALE


def test_future_observation_is_invalid_not_stale() -> None:
    evaluated_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="freshness durations"):
        assess_freshness(
            evaluated_at + timedelta(seconds=1), evaluated_at, timedelta(seconds=120)
        )
