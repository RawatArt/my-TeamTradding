from tests.fakes.risk import CYCLE_ID, SNAPSHOT_ID

from ai_trading_team.orchestration.identifiers import logical_invocation_id
from ai_trading_team.schemas.enums import AgentRole


def test_logical_invocation_identity_is_deterministic_and_attempt_independent() -> None:
    first = logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 1, AgentRole.TREND_ANALYST)
    second = logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 1, AgentRole.TREND_ANALYST)
    assert first == second


def test_stage_role_and_debate_round_change_logical_identity() -> None:
    identities = {
        logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 1, AgentRole.TREND_ANALYST),
        logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 2, AgentRole.TREND_ANALYST),
        logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 4, AgentRole.SKEPTIC, 1),
        logical_invocation_id(CYCLE_ID, SNAPSHOT_ID, 4, AgentRole.SKEPTIC, 2),
    }
    assert len(identities) == 4
