"""M4 deterministic orchestration metadata and interfaces; no trading loop exists."""

from ai_trading_team.orchestration.debate import DebatePolicy
from ai_trading_team.orchestration.failures import AgentFailurePolicy
from ai_trading_team.orchestration.preflight import ShadowPreflightError, validate_shadow_inputs
from ai_trading_team.orchestration.protocols import AgentOrchestrator, DeterministicRiskStage
from ai_trading_team.orchestration.runtime import (
    AgentRuntimeAssignment,
    RuntimeAgentInvoker,
    ShadowAgentInvoker,
)
from ai_trading_team.orchestration.shadow import ShadowCycleOrchestrator, ShadowCyclePolicy
from ai_trading_team.orchestration.stages import (
    COMPONENT_DEPENDENCIES,
    REALTIME_DECISION_STAGES,
    RETROSPECTIVE_REVIEW_STAGES,
    validate_pipeline,
)

__all__ = [
    "AgentFailurePolicy",
    "AgentRuntimeAssignment",
    "AgentOrchestrator",
    "COMPONENT_DEPENDENCIES",
    "DebatePolicy",
    "DeterministicRiskStage",
    "REALTIME_DECISION_STAGES",
    "RETROSPECTIVE_REVIEW_STAGES",
    "RuntimeAgentInvoker",
    "ShadowAgentInvoker",
    "ShadowCycleOrchestrator",
    "ShadowCyclePolicy",
    "ShadowPreflightError",
    "validate_shadow_inputs",
    "validate_pipeline",
]
