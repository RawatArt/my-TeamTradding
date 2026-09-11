"""Immutable least-privilege role access and execution-profile policy."""

from types import MappingProxyType
from typing import Final

from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentRole,
    InformationResource,
)

ROLE_INFORMATION_ACCESS: Final = MappingProxyType(
    {
        AgentRole.MARKET_CONTEXT: frozenset({InformationResource.MARKET_SNAPSHOT_VIEW}),
        AgentRole.TREND_ANALYST: frozenset({InformationResource.MARKET_SNAPSHOT_VIEW}),
        AgentRole.PRICE_ACTION_ANALYST: frozenset(
            {InformationResource.MARKET_SNAPSHOT_VIEW}
        ),
        AgentRole.ENTRY_ANALYST: frozenset(
            {
                InformationResource.MARKET_SNAPSHOT_VIEW,
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
            }
        ),
        AgentRole.QUANT_RESEARCHER: frozenset(
            {
                InformationResource.MARKET_SNAPSHOT_VIEW,
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
                InformationResource.QUANTITATIVE_EVIDENCE,
                InformationResource.PERFORMANCE_HISTORY,
            }
        ),
        AgentRole.SENIOR_QUANT_DEVELOPER: frozenset(
            {
                InformationResource.MARKET_SNAPSHOT_VIEW,
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
                InformationResource.QUANTITATIVE_EVIDENCE,
                InformationResource.PERFORMANCE_HISTORY,
            }
        ),
        AgentRole.SKEPTIC: frozenset(
            {
                InformationResource.MARKET_SNAPSHOT_VIEW,
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
                InformationResource.TRADE_PROPOSAL,
                InformationResource.QUANTITATIVE_EVIDENCE,
            }
        ),
        AgentRole.CHIEF_TRADER: frozenset(
            {
                InformationResource.MARKET_SNAPSHOT_VIEW,
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
                InformationResource.TRADE_PROPOSAL,
                InformationResource.QUANTITATIVE_EVIDENCE,
            }
        ),
        AgentRole.PERFORMANCE_REVIEWER: frozenset(
            {
                InformationResource.UPSTREAM_AGENT_OUTPUTS,
                InformationResource.TRADE_PROPOSAL,
                InformationResource.QUANTITATIVE_EVIDENCE,
                InformationResource.RISK_DECISION,
                InformationResource.PERFORMANCE_HISTORY,
            }
        ),
    }
)

ROLE_EXECUTION_PROFILES: Final = MappingProxyType(
    {
        AgentRole.MARKET_CONTEXT: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.TREND_ANALYST: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.PRICE_ACTION_ANALYST: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.ENTRY_ANALYST: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.QUANT_RESEARCHER: frozenset(
            {AgentExecutionProfile.CONDITIONAL, AgentExecutionProfile.OFFLINE}
        ),
        AgentRole.SENIOR_QUANT_DEVELOPER: frozenset(
            {AgentExecutionProfile.CONDITIONAL, AgentExecutionProfile.OFFLINE}
        ),
        AgentRole.SKEPTIC: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.CHIEF_TRADER: frozenset({AgentExecutionProfile.REALTIME}),
        AgentRole.PERFORMANCE_REVIEWER: frozenset({AgentExecutionProfile.OFFLINE}),
    }
)


def can_access(role: AgentRole, resource: InformationResource) -> bool:
    """Return the fixed M4 access decision for a role and resource."""
    return resource in ROLE_INFORMATION_ACCESS[role]


def execution_profile_allowed(role: AgentRole, profile: AgentExecutionProfile) -> bool:
    """Return whether a configured role supports the selected inert profile."""
    return profile in ROLE_EXECUTION_PROFILES[role]
