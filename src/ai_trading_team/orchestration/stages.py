"""Immutable M4 realtime and retrospective stage definitions."""

from types import MappingProxyType
from typing import Final

from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    PipelineComponent,
    PipelineKind,
)
from ai_trading_team.schemas.orchestration import StageDefinition, StageMember

REALTIME_DECISION_STAGES: Final = (
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=1,
        name="parallel-analysis",
        members=(
            StageMember(
                component=PipelineComponent.MARKET_CONTEXT,
                required=False,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
            StageMember(
                component=PipelineComponent.TREND_ANALYST,
                required=False,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
            StageMember(
                component=PipelineComponent.PRICE_ACTION_ANALYST,
                required=False,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
        ),
        parallel=True,
        minimum_successes=2,
    ),
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=2,
        name="entry-analysis",
        members=(
            StageMember(
                component=PipelineComponent.ENTRY_ANALYST,
                required=True,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
        ),
        minimum_successes=1,
    ),
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=3,
        name="conditional-quant-review",
        members=(
            StageMember(
                component=PipelineComponent.QUANT_RESEARCHER,
                required=False,
                allowed_profiles=(AgentExecutionProfile.CONDITIONAL,),
            ),
            StageMember(
                component=PipelineComponent.SENIOR_QUANT_DEVELOPER,
                required=False,
                allowed_profiles=(AgentExecutionProfile.CONDITIONAL,),
            ),
        ),
        parallel=False,
        minimum_successes=0,
    ),
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=4,
        name="skeptic-review",
        members=(
            StageMember(
                component=PipelineComponent.SKEPTIC,
                required=True,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
        ),
        minimum_successes=1,
    ),
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=5,
        name="chief-decision",
        members=(
            StageMember(
                component=PipelineComponent.CHIEF_TRADER,
                required=True,
                allowed_profiles=(AgentExecutionProfile.REALTIME,),
            ),
        ),
        minimum_successes=1,
    ),
    StageDefinition(
        pipeline=PipelineKind.REALTIME_DECISION,
        stage_number=6,
        name="deterministic-risk",
        members=(
            StageMember(
                component=PipelineComponent.RISK_ENGINE,
                required=True,
            ),
        ),
        minimum_successes=1,
    ),
)

RETROSPECTIVE_REVIEW_STAGES: Final = (
    StageDefinition(
        pipeline=PipelineKind.RETROSPECTIVE_REVIEW,
        stage_number=1,
        name="performance-review",
        members=(
            StageMember(
                component=PipelineComponent.PERFORMANCE_REVIEWER,
                required=False,
                allowed_profiles=(AgentExecutionProfile.OFFLINE,),
            ),
        ),
        minimum_successes=0,
    ),
)

COMPONENT_DEPENDENCIES: Final = MappingProxyType(
    {
        PipelineComponent.MARKET_CONTEXT: frozenset(),
        PipelineComponent.TREND_ANALYST: frozenset(),
        PipelineComponent.PRICE_ACTION_ANALYST: frozenset(),
        PipelineComponent.ENTRY_ANALYST: frozenset(
            {
                PipelineComponent.MARKET_CONTEXT,
                PipelineComponent.TREND_ANALYST,
                PipelineComponent.PRICE_ACTION_ANALYST,
            }
        ),
        PipelineComponent.QUANT_RESEARCHER: frozenset({PipelineComponent.ENTRY_ANALYST}),
        PipelineComponent.SENIOR_QUANT_DEVELOPER: frozenset(
            {PipelineComponent.ENTRY_ANALYST}
        ),
        PipelineComponent.SKEPTIC: frozenset({PipelineComponent.ENTRY_ANALYST}),
        PipelineComponent.CHIEF_TRADER: frozenset(
            {PipelineComponent.ENTRY_ANALYST, PipelineComponent.SKEPTIC}
        ),
        PipelineComponent.RISK_ENGINE: frozenset({PipelineComponent.CHIEF_TRADER}),
        PipelineComponent.PERFORMANCE_REVIEWER: frozenset(),
    }
)


def validate_pipeline(stages: tuple[StageDefinition, ...]) -> None:
    """Reject non-sequential stages, duplicates, and future dependencies."""
    if not stages:
        raise ValueError("pipeline must contain at least one stage")
    expected_numbers = tuple(range(1, len(stages) + 1))
    if tuple(stage.stage_number for stage in stages) != expected_numbers:
        raise ValueError("pipeline stage numbers must be consecutive and ordered")
    if len({stage.pipeline for stage in stages}) != 1:
        raise ValueError("all stages must belong to one pipeline")

    seen: set[PipelineComponent] = set()
    for stage in stages:
        for member in stage.members:
            if member.component in seen:
                raise ValueError("pipeline component must appear exactly once")
            dependencies = COMPONENT_DEPENDENCIES[member.component]
            if not dependencies.issubset(seen):
                raise ValueError("component dependency must occur in an earlier stage")
            seen.add(member.component)


validate_pipeline(REALTIME_DECISION_STAGES)
validate_pipeline(RETROSPECTIVE_REVIEW_STAGES)
