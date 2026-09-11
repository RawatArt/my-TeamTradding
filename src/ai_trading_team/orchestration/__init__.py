"""M4 deterministic orchestration metadata and interfaces; no trading loop exists."""

from ai_trading_team.orchestration.debate import DebatePolicy
from ai_trading_team.orchestration.failures import AgentFailurePolicy
from ai_trading_team.orchestration.protocols import AgentOrchestrator, DeterministicRiskStage
from ai_trading_team.orchestration.stages import (
    COMPONENT_DEPENDENCIES,
    REALTIME_DECISION_STAGES,
    RETROSPECTIVE_REVIEW_STAGES,
    validate_pipeline,
)

__all__ = [
    "AgentFailurePolicy",
    "AgentOrchestrator",
    "COMPONENT_DEPENDENCIES",
    "DebatePolicy",
    "DeterministicRiskStage",
    "REALTIME_DECISION_STAGES",
    "RETROSPECTIVE_REVIEW_STAGES",
    "validate_pipeline",
]
