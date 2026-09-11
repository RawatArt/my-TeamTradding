"""Mandatory M8 decision/outcome, partition, and capability safety tests."""

from decimal import Decimal
from pathlib import Path

import pytest
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
from ai_trading_team.replay import ReplayError
from ai_trading_team.replay.engine import freeze_replay_decision
from ai_trading_team.replay.serialization import dataset_digest
from ai_trading_team.schemas.enums import (
    ReplayDecisionSource,
    Timeframe,
    TradeOutcomeStatus,
)


def test_final_decision_candle_cannot_resolve_or_affect_future_excursions() -> None:
    dataset = replay_dataset(
        future_m15=(
            (
                Decimal("1.08130"),
                Decimal("1.08140"),
                Decimal("1.08120"),
                Decimal("1.08130"),
            ),
        )
    )
    candles = tuple(
        candle.model_copy(
            update={"high": Decimal("1.09000"), "low": Decimal("1.07000")}
        )
        if candle.timeframe is Timeframe.M15 and candle.close_time == REPLAY_CUTOFF
        else candle
        for candle in dataset.candles
    )
    changed = dataset.model_copy(update={"candles": candles})
    changed = changed.model_copy(update={"dataset_digest": dataset_digest(changed)})
    _, source, _, result = replay_build(changed)
    configuration = replay_configuration(changed, max_bars=1)
    frozen = freeze_replay_decision(
        result.frame,
        replay_proposal(result),
        source=ReplayDecisionSource.SCRIPTED,
        frozen_at=REPLAY_CUTOFF,
    )
    view = source.outcome_view(
        frozen, PARTITION_ID, Timeframe.M15, configuration.outcome_horizon
    )
    outcome = OutcomeEvaluator().evaluate(result.frame, frozen, view, configuration)
    assert view.candles[0].open_time == REPLAY_CUTOFF
    assert outcome.status is TradeOutcomeStatus.UNRESOLVED_HORIZON
    assert outcome.maximum_favorable_excursion == Decimal("0.00010")
    assert outcome.maximum_adverse_excursion == Decimal("0.00010")


def test_outcome_terminates_before_later_extreme_candles() -> None:
    from tests.unit.test_trade_outcomes import _evaluate

    outcome = _evaluate(
        (
            (Decimal("1.08130"), Decimal("1.08165"), Decimal("1.08120"), Decimal("1.08150")),
            (Decimal("1.08150"), Decimal("2.00000"), Decimal("0.50000"), Decimal("1.00000")),
        )
    )
    assert outcome.bars_evaluated == 1
    assert outcome.maximum_favorable_excursion == Decimal("0.00035")


def test_warmup_range_cannot_create_frame_or_cross_evaluation_end() -> None:
    dataset, source, configuration, result = replay_build()
    partition = dataset.metadata.partitions[0]
    with pytest.raises(ReplayError):
        source.decision_view(PARTITION_ID, partition.evaluation_start.replace(day=9))
    frozen = freeze_replay_decision(
        result.frame,
        replay_proposal(result),
        source=ReplayDecisionSource.SCRIPTED,
        frozen_at=REPLAY_CUTOFF,
    )
    view = source.outcome_view(
        frozen, PARTITION_ID, Timeframe.M15, configuration.outcome_horizon
    )
    assert all(candle.close_time <= partition.evaluation_end for candle in view.candles)


def test_mismatched_risk_decision_cannot_be_frozen() -> None:
    _, _, _, result = replay_build()
    proposal = replay_proposal(result)
    risk = replay_risk_decision(result, proposal).model_copy(
        update={"snapshot_id": "mismatched-snapshot"}
    )
    with pytest.raises(ReplayError):
        freeze_replay_decision(
            result.frame,
            proposal,
            source=ReplayDecisionSource.PERSISTED_RECORD,
            frozen_at=REPLAY_CUTOFF,
            risk_decision=risk,
        )


def test_replay_packages_have_no_forbidden_runtime_capabilities() -> None:
    root = Path(__file__).parents[2] / "src" / "ai_trading_team"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for package in (root / "replay", root / "evaluation")
        for path in package.glob("*.py")
    ).lower()
    for forbidden in (
        "metatrader5",
        "order_send",
        "symbol_select",
        "openai",
        "anthropic",
        "google.genai",
        "hyperparameter",
        "prompt optimization",
    ):
        assert forbidden not in text
