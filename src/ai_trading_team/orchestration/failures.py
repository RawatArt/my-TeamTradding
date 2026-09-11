"""Pure deterministic failure and stale-snapshot policy."""

from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    AgentRole,
    FailureDisposition,
    FreshnessState,
)

_STAGE_ONE_ROLES = frozenset(
    {AgentRole.MARKET_CONTEXT, AgentRole.TREND_ANALYST, AgentRole.PRICE_ACTION_ANALYST}
)


class AgentFailurePolicy:
    """Map explicit failure facts to a safe outcome without invoking an agent."""

    @staticmethod
    def resolve(
        category: AgentFailureCategory,
        *,
        role: AgentRole | None = None,
        stage_one_successes: int = 0,
    ) -> FailureDisposition:
        if stage_one_successes < 0 or stage_one_successes > 3:
            raise ValueError("stage_one_successes must be between zero and three")
        if category in {
            AgentFailureCategory.INVALID_SNAPSHOT,
            AgentFailureCategory.SCHEMA_MISMATCH,
            AgentFailureCategory.UNKNOWN,
        }:
            return FailureDisposition.ABORT_CYCLE
        if category in {
            AgentFailureCategory.STALE_SNAPSHOT,
            AgentFailureCategory.MISSING_REQUIRED_UPSTREAM,
        }:
            return FailureDisposition.HOLD
        if category is AgentFailureCategory.INVALID_OUTPUT:
            return (
                FailureDisposition.CONTINUE_DEGRADED
                if role is AgentRole.PERFORMANCE_REVIEWER
                else FailureDisposition.HOLD
            )
        if category in {
            AgentFailureCategory.TIMEOUT,
            AgentFailureCategory.UNAVAILABLE_AGENT,
        }:
            if role in {
                AgentRole.QUANT_RESEARCHER,
                AgentRole.SENIOR_QUANT_DEVELOPER,
                AgentRole.PERFORMANCE_REVIEWER,
            }:
                return FailureDisposition.CONTINUE_DEGRADED
            if role in _STAGE_ONE_ROLES and stage_one_successes >= 2:
                return FailureDisposition.CONTINUE_DEGRADED
            return FailureDisposition.HOLD
        return FailureDisposition.ABORT_CYCLE

    @staticmethod
    def stale_snapshot_disposition(
        market: AgentMarketView,
    ) -> FailureDisposition | None:
        """Keep M2 validity intact while defaulting a stale decision input to HOLD."""
        if market.freshness.overall is FreshnessState.STALE:
            return FailureDisposition.HOLD
        return None
