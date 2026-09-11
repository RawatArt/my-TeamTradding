from datetime import UTC, datetime

import pytest

from ai_trading_team.config import AgentFrameworkSettings
from ai_trading_team.orchestration import DebatePolicy
from ai_trading_team.schemas.agents import AgentEvidence
from ai_trading_team.schemas.enums import AgentRole, EvidenceKind
from ai_trading_team.schemas.orchestration import DebateChallenge


def challenge(round_number: int = 1) -> DebateChallenge:
    return DebateChallenge(
        challenge_id=f"challenge-{round_number}",
        cycle_id="cycle-m4",
        snapshot_id="snapshot-m4",
        round_number=round_number,
        target=AgentRole.CHIEF_TRADER,
        challenged_output_id="chief-draft-1",
        objections=(
            AgentEvidence(
                evidence_id="objection-1",
                kind=EvidenceKind.INTERPRETATION,
                summary="The entry assumption is unsupported",
            ),
        ),
        produced_at=datetime(2026, 9, 11, tzinfo=UTC),
    )


def test_debate_defaults_to_one_round() -> None:
    policy = DebatePolicy(AgentFrameworkSettings())

    assert policy.max_rounds == 1
    assert policy.can_start_round(0)
    assert not policy.can_start_round(1)
    policy.validate_challenge(challenge())


def test_debate_can_be_disabled() -> None:
    policy = DebatePolicy(AgentFrameworkSettings(max_debate_rounds=0))

    assert not policy.can_start_round(0)
    with pytest.raises(ValueError, match="round limit"):
        policy.validate_challenge(challenge())


def test_challenge_beyond_configured_limit_is_rejected() -> None:
    policy = DebatePolicy(AgentFrameworkSettings(max_debate_rounds=1))

    with pytest.raises(ValueError, match="round limit"):
        policy.validate_challenge(challenge(round_number=2))


def test_challenge_round_must_follow_completed_round_monotonically() -> None:
    policy = DebatePolicy(AgentFrameworkSettings(max_debate_rounds=3))

    policy.validate_challenge(challenge(round_number=2), completed_rounds=1)
    with pytest.raises(ValueError, match="monotonically"):
        policy.validate_challenge(challenge(round_number=2), completed_rounds=0)


def test_only_skeptic_can_challenge_entry_or_chief() -> None:
    assert challenge().challenger is AgentRole.SKEPTIC

    payload = challenge().model_dump(mode="python")
    payload["challenger"] = AgentRole.TREND_ANALYST
    with pytest.raises(ValueError):
        DebateChallenge.model_validate(payload)

    payload = challenge().model_dump(mode="python")
    payload["target"] = AgentRole.SKEPTIC
    with pytest.raises(ValueError):
        DebateChallenge.model_validate(payload)


def test_maximum_debate_rounds_has_hard_ceiling() -> None:
    with pytest.raises(ValueError):
        AgentFrameworkSettings(max_debate_rounds=4)
