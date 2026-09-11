import pytest

from ai_trading_team.orchestration.stages import (
    COMPONENT_DEPENDENCIES,
    REALTIME_DECISION_STAGES,
    RETROSPECTIVE_REVIEW_STAGES,
    validate_pipeline,
)
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    PipelineComponent,
    PipelineKind,
)


def components(stage_number: int) -> tuple[PipelineComponent, ...]:
    return tuple(
        member.component for member in REALTIME_DECISION_STAGES[stage_number - 1].members
    )


def test_realtime_stage_order_is_exact_and_risk_is_last() -> None:
    assert components(1) == (
        PipelineComponent.MARKET_CONTEXT,
        PipelineComponent.TREND_ANALYST,
        PipelineComponent.PRICE_ACTION_ANALYST,
    )
    assert components(2) == (PipelineComponent.ENTRY_ANALYST,)
    assert components(3) == (
        PipelineComponent.QUANT_RESEARCHER,
        PipelineComponent.SENIOR_QUANT_DEVELOPER,
    )
    assert components(4) == (PipelineComponent.SKEPTIC,)
    assert components(5) == (PipelineComponent.CHIEF_TRADER,)
    assert components(6) == (PipelineComponent.RISK_ENGINE,)


def test_only_stage_one_is_parallel() -> None:
    assert REALTIME_DECISION_STAGES[0].parallel
    assert all(not stage.parallel for stage in REALTIME_DECISION_STAGES[1:])
    assert REALTIME_DECISION_STAGES[0].minimum_successes == 2


def test_quant_stage_is_conditional_and_not_mandatory() -> None:
    stage = REALTIME_DECISION_STAGES[2]

    assert stage.minimum_successes == 0
    assert all(not member.required for member in stage.members)
    assert all(
        member.allowed_profiles == (AgentExecutionProfile.CONDITIONAL,)
        for member in stage.members
    )


def test_performance_reviewer_is_only_in_retrospective_pipeline() -> None:
    realtime_components = {
        member.component for stage in REALTIME_DECISION_STAGES for member in stage.members
    }
    retrospective = RETROSPECTIVE_REVIEW_STAGES[0]

    assert PipelineComponent.PERFORMANCE_REVIEWER not in realtime_components
    assert retrospective.pipeline is PipelineKind.RETROSPECTIVE_REVIEW
    assert tuple(member.component for member in retrospective.members) == (
        PipelineComponent.PERFORMANCE_REVIEWER,
    )
    assert retrospective.members[0].allowed_profiles == (AgentExecutionProfile.OFFLINE,)


def test_dependencies_are_acyclic_and_always_point_backward() -> None:
    stage_by_component = {
        member.component: stage.stage_number
        for stage in REALTIME_DECISION_STAGES
        for member in stage.members
    }

    for component, dependencies in COMPONENT_DEPENDENCIES.items():
        if component is PipelineComponent.PERFORMANCE_REVIEWER:
            continue
        assert all(
            stage_by_component[item] < stage_by_component[component]
            for item in dependencies
        )


def test_pipeline_validator_rejects_reordered_stages() -> None:
    reordered = (
        REALTIME_DECISION_STAGES[1],
        REALTIME_DECISION_STAGES[0],
        *REALTIME_DECISION_STAGES[2:],
    )

    with pytest.raises(ValueError, match="consecutive and ordered"):
        validate_pipeline(reordered)
