"""Bounded Skeptic challenge policy; no conversational runtime exists in M4."""

from ai_trading_team.config.settings import AgentFrameworkSettings
from ai_trading_team.schemas.orchestration import DebateChallenge


class DebatePolicy:
    """Validate monotonic, bounded debate rounds controlled by an orchestrator."""

    def __init__(self, settings: AgentFrameworkSettings) -> None:
        self._max_rounds = settings.max_debate_rounds

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    def can_start_round(self, completed_rounds: int) -> bool:
        if completed_rounds < 0:
            raise ValueError("completed_rounds must not be negative")
        return completed_rounds < self._max_rounds

    def validate_challenge(
        self,
        challenge: DebateChallenge,
        *,
        completed_rounds: int = 0,
    ) -> None:
        if completed_rounds < 0:
            raise ValueError("completed_rounds must not be negative")
        if challenge.round_number > self._max_rounds:
            raise ValueError("challenge exceeds configured debate-round limit")
        if challenge.round_number != completed_rounds + 1:
            raise ValueError("challenge round must follow the completed round monotonically")
