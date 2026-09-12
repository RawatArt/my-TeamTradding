"""M9 separation and immutable attachment of accepted M8 outcomes."""

from datetime import timedelta
from decimal import Decimal

from tests.fakes.replay import (
    PARTITION_ID,
    REPLAY_CUTOFF,
    replay_build,
    replay_configuration,
    replay_dataset,
    replay_proposal,
    replay_risk_decision,
)

from ai_trading_team.evaluation import OutcomeEvaluator
from ai_trading_team.observation.outcomes import ShadowOutcomeTracker
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import OutcomeTrackingState, Timeframe
from ai_trading_team.schemas.evaluation import SegmentFacts
from ai_trading_team.schemas.observation import PendingShadowOutcome
from ai_trading_team.schemas.shadow import ShadowTradeIntent
from ai_trading_team.storage.observation import InMemoryObservationRepository


def test_m8_outcome_attaches_without_changing_frozen_shadow_intent() -> None:
    dataset = replay_dataset(
        future_m15=(
            (
                Decimal("1.08130"),
                Decimal("1.08165"),
                Decimal("1.08120"),
                Decimal("1.08150"),
            ),
        )
    )
    _, source, _, result = replay_build(dataset)
    configuration = replay_configuration(dataset, max_bars=1)
    proposal = replay_proposal(result)
    risk = replay_risk_decision(result, proposal)
    assert risk.position_sizing is not None
    assert risk.position_sizing.selected_volume is not None
    assert proposal.entry is not None
    assert proposal.stop_loss is not None
    assert proposal.take_profit is not None
    intent = ShadowTradeIntent(
        cycle_id=proposal.cycle_id,
        snapshot_id=proposal.snapshot_id,
        proposal=proposal,
        risk_decision=risk,
        selected_volume=risk.position_sizing.selected_volume,
        hypothetical_entry=proposal.entry,
        hypothetical_stop_loss=proposal.stop_loss,
        hypothetical_take_profit=proposal.take_profit,
        recorded_at=REPLAY_CUTOFF,
    )
    facts = SegmentFacts(
        direction=proposal.side,
        timeframe=Timeframe.M15,
        partition=result.frame.partition_kind,
    )
    pending = PendingShadowOutcome(
        tracking_id="outcome-tracking-m9-001",
        decision_record_id="decision-record-m9-001",
        decision_record_digest="sha256:" + "d" * 64,
        shadow_intent=intent,
        decision_candle_close_at=REPLAY_CUTOFF,
        horizon=configuration.outcome_horizon,
        segment_facts=facts,
        created_at=REPLAY_CUTOFF,
        updated_at=REPLAY_CUTOFF,
    )
    repository = InMemoryObservationRepository()
    repository.append_pending_outcome(pending)
    from ai_trading_team.replay.engine import freeze_replay_decision
    from ai_trading_team.schemas.enums import ReplayDecisionSource

    frozen = freeze_replay_decision(
        result.frame,
        proposal,
        source=ReplayDecisionSource.SCRIPTED,
        frozen_at=REPLAY_CUTOFF,
    )
    view = source.outcome_view(
        frozen,
        PARTITION_ID,
        Timeframe.M15,
        configuration.outcome_horizon,
    )
    outcome = OutcomeEvaluator().evaluate(
        result.frame,
        frozen,
        view,
        configuration,
        segment_facts=facts,
    )

    terminal = ShadowOutcomeTracker(repository).attach(
        pending.tracking_id,
        outcome,
        at=REPLAY_CUTOFF + timedelta(minutes=15),
    )

    assert terminal.state is OutcomeTrackingState.RESOLVED
    assert terminal.shadow_intent == pending.shadow_intent
    assert content_digest(terminal.shadow_intent) == content_digest(pending.shadow_intent)
    assert repository.pending_outcomes() == ()
