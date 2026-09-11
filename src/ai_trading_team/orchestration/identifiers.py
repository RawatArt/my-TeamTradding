"""Deterministic identities for one immutable decision-cycle structure."""

from hashlib import sha256

from ai_trading_team.schemas.common import Identifier
from ai_trading_team.schemas.enums import AgentRole


def logical_invocation_id(
    cycle_id: str,
    snapshot_id: str,
    stage_number: int,
    role: AgentRole,
    debate_round: int | None = None,
) -> Identifier:
    """Derive one stable logical ID; provider attempts do not change it."""
    round_value = debate_round or 0
    material = (
        f"m6-invocation-v1\0{cycle_id}\0{snapshot_id}\0{stage_number}"
        f"\0{role.value}\0{round_value}"
    ).encode()
    return f"inv-m6-{sha256(material).hexdigest()}"


def logical_output_id(invocation_id: str) -> Identifier:
    """Derive the trusted output ID from its logical invocation."""
    return f"out-m6-{sha256(invocation_id.encode()).hexdigest()}"


def shadow_record_id(cycle_id: str, snapshot_id: str) -> Identifier:
    """Derive one stable final audit-record identity."""
    material = f"m6-record-v1\0{cycle_id}\0{snapshot_id}".encode()
    return f"shadow-m6-{sha256(material).hexdigest()}"
