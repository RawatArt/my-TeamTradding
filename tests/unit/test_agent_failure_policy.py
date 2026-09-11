from datetime import timedelta

import pytest
from tests.fakes.agents import market_view
from tests.fakes.market import SNAPSHOT_END

from ai_trading_team.orchestration import AgentFailurePolicy
from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    AgentRole,
    FailureDisposition,
    FreshnessState,
)


@pytest.mark.parametrize(
    "category",
    [
        AgentFailureCategory.INVALID_SNAPSHOT,
        AgentFailureCategory.SCHEMA_MISMATCH,
        AgentFailureCategory.UNKNOWN,
    ],
)
def test_invalid_or_incompatible_inputs_abort_cycle(category: AgentFailureCategory) -> None:
    assert AgentFailurePolicy.resolve(category) is FailureDisposition.ABORT_CYCLE


@pytest.mark.parametrize(
    "category",
    [
        AgentFailureCategory.STALE_SNAPSHOT,
        AgentFailureCategory.MISSING_REQUIRED_UPSTREAM,
        AgentFailureCategory.INVALID_OUTPUT,
    ],
)
def test_unsafe_decision_inputs_default_to_hold(category: AgentFailureCategory) -> None:
    assert AgentFailurePolicy.resolve(category) is FailureDisposition.HOLD


@pytest.mark.parametrize(
    "category",
    [AgentFailureCategory.TIMEOUT, AgentFailureCategory.UNAVAILABLE_AGENT],
)
def test_one_stage_one_availability_failure_can_continue_with_quorum(
    category: AgentFailureCategory,
) -> None:
    assert (
        AgentFailurePolicy.resolve(
            category,
            role=AgentRole.TREND_ANALYST,
            stage_one_successes=2,
        )
        is FailureDisposition.CONTINUE_DEGRADED
    )
    assert (
        AgentFailurePolicy.resolve(
            category,
            role=AgentRole.TREND_ANALYST,
            stage_one_successes=1,
        )
        is FailureDisposition.HOLD
    )


def test_conditional_quant_role_availability_failures_can_degrade() -> None:
    assert (
        AgentFailurePolicy.resolve(
            AgentFailureCategory.TIMEOUT,
            role=AgentRole.QUANT_RESEARCHER,
        )
        is FailureDisposition.CONTINUE_DEGRADED
    )
    assert (
        AgentFailurePolicy.resolve(
            AgentFailureCategory.TIMEOUT,
            role=AgentRole.SENIOR_QUANT_DEVELOPER,
        )
        is FailureDisposition.CONTINUE_DEGRADED
    )


def test_performance_failure_does_not_affect_current_decision_cycle() -> None:
    for category in (
        AgentFailureCategory.TIMEOUT,
        AgentFailureCategory.UNAVAILABLE_AGENT,
        AgentFailureCategory.INVALID_OUTPUT,
    ):
        assert (
            AgentFailurePolicy.resolve(category, role=AgentRole.PERFORMANCE_REVIEWER)
            is FailureDisposition.CONTINUE_DEGRADED
        )


def test_stale_policy_does_not_change_valid_market_view() -> None:
    view = market_view()
    before = view.model_dump_json()

    disposition = AgentFailurePolicy.stale_snapshot_disposition(view)

    assert disposition is None
    assert view.model_dump_json() == before


def test_stale_but_valid_view_maps_to_hold_only_in_orchestration_policy() -> None:
    payload = market_view().model_dump(mode="python")
    observed_at = SNAPSHOT_END - timedelta(seconds=10)
    payload["tick"]["source_time"] = observed_at
    payload["freshness"]["tick"].update(
        observed_at=observed_at,
        evaluated_at=SNAPSHOT_END,
        age=timedelta(seconds=10),
        maximum_age=timedelta(seconds=1),
        state=FreshnessState.STALE,
    )
    payload["freshness"]["overall"] = FreshnessState.STALE
    stale_view = AgentMarketView.model_validate(payload)

    assert (
        AgentFailurePolicy.stale_snapshot_disposition(stale_view)
        is FailureDisposition.HOLD
    )
    assert stale_view.freshness.overall is FreshnessState.STALE


def test_failure_policy_is_deterministic() -> None:
    first = AgentFailurePolicy.resolve(
        AgentFailureCategory.UNAVAILABLE_AGENT,
        role=AgentRole.PRICE_ACTION_ANALYST,
        stage_one_successes=2,
    )
    second = AgentFailurePolicy.resolve(
        AgentFailureCategory.UNAVAILABLE_AGENT,
        role=AgentRole.PRICE_ACTION_ANALYST,
        stage_one_successes=2,
    )

    assert first is second


def test_invalid_stage_one_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="between zero and three"):
        AgentFailurePolicy.resolve(
            AgentFailureCategory.TIMEOUT,
            role=AgentRole.TREND_ANALYST,
            stage_one_successes=4,
        )
