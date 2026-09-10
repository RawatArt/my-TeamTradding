"""Minimal structured-output boundary for future agents."""

from ai_trading_team.schemas.common import AgentName, Confidence, SchemaVersion, TraceableRecord
from ai_trading_team.schemas.enums import TradeAction


class AgentOutput(TraceableRecord):
    """Traceable common fields that future role-specific outputs may extend."""

    agent: AgentName
    agent_version: SchemaVersion
    decision: TradeAction
    confidence: Confidence
    evidence: tuple[str, ...] = ()
    invalidations: tuple[str, ...] = ()

