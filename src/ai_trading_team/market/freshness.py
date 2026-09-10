"""Pure deterministic freshness classification for valid observations."""

from datetime import datetime, timedelta

from ai_trading_team.schemas.enums import FreshnessState
from ai_trading_team.schemas.market import ObservationFreshness


def assess_freshness(
    observed_at: datetime,
    evaluated_at: datetime,
    maximum_age: timedelta,
) -> ObservationFreshness:
    """Classify age without deciding validity or tradeability."""
    age = evaluated_at - observed_at
    state = FreshnessState.FRESH if age <= maximum_age else FreshnessState.STALE
    return ObservationFreshness(
        observed_at=observed_at,
        evaluated_at=evaluated_at,
        age=age,
        maximum_age=maximum_age,
        state=state,
    )
