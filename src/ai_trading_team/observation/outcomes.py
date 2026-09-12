"""Separate attachment of accepted M8 outcomes to frozen M9 shadow decisions."""

import hashlib
from datetime import UTC, datetime

from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import OutcomeTrackingState, TradeOutcomeStatus
from ai_trading_team.schemas.evaluation import SegmentFacts, TradeOutcome
from ai_trading_team.schemas.observation import (
    ContinuousDecisionRecord,
    PendingShadowOutcome,
)
from ai_trading_team.schemas.replay import OutcomeHorizon
from ai_trading_team.storage.observation import ObservationRepository


class ShadowOutcomeTracker:
    """Track M8-evaluated results without modifying the frozen M9 decision."""

    def __init__(self, repository: ObservationRepository) -> None:
        self._repository = repository

    def register(
        self,
        decision: ContinuousDecisionRecord,
        *,
        decision_candle_close_at: datetime,
        horizon: OutcomeHorizon,
        segment_facts: SegmentFacts,
        at: datetime,
    ) -> PendingShadowOutcome | None:
        intent = (
            None
            if decision.shadow_record is None
            else decision.shadow_record.shadow_trade_intent
        )
        if intent is None:
            return None
        timestamp = _utc(at)
        tracking_id = "outcome-m9-" + hashlib.sha256(
            decision.record_id.encode("utf-8")
        ).hexdigest()
        pending = PendingShadowOutcome(
            tracking_id=tracking_id,
            decision_record_id=decision.record_id,
            decision_record_digest=content_digest(decision),
            shadow_intent=intent,
            decision_candle_close_at=decision_candle_close_at,
            horizon=horizon,
            segment_facts=segment_facts,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._repository.append_pending_outcome(pending)
        return pending

    def attach(
        self,
        tracking_id: str,
        outcome: TradeOutcome,
        *,
        at: datetime,
    ) -> PendingShadowOutcome:
        pending = self._repository.get_outcome(tracking_id)
        if pending is None or pending.state is not OutcomeTrackingState.PENDING:
            raise ValueError("outcome tracking record is missing or already terminal")
        intent = pending.shadow_intent
        if (
            outcome.cycle_id != intent.cycle_id
            or outcome.snapshot_id != intent.snapshot_id
            or outcome.proposal_id != intent.proposal.proposal_id
            or outcome.proposal_digest != content_digest(intent.proposal)
            or outcome.symbol != intent.proposal.symbol
            or outcome.decision_cutoff != pending.decision_candle_close_at
            or outcome.horizon != pending.horizon
            or outcome.segment_facts != pending.segment_facts
        ):
            raise ValueError("M8 outcome does not match the frozen M9 decision")
        state = {
            TradeOutcomeStatus.TAKE_PROFIT_REACHED: OutcomeTrackingState.RESOLVED,
            TradeOutcomeStatus.STOP_LOSS_REACHED: OutcomeTrackingState.RESOLVED,
            TradeOutcomeStatus.AMBIGUOUS_INTRABAR: OutcomeTrackingState.AMBIGUOUS,
            TradeOutcomeStatus.UNRESOLVED_HORIZON: OutcomeTrackingState.UNRESOLVED_HORIZON,
        }[outcome.status]
        terminal = PendingShadowOutcome.model_validate(
            pending.model_copy(
                update={
                    "state": state,
                    "updated_at": _utc(at),
                    "outcome": outcome,
                }
            ).model_dump()
        )
        self._repository.update_outcome(terminal)
        return terminal


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("outcome tracking timestamp must be timezone-aware")
    return value.astimezone(UTC)
