"""Tests for deterministic R-sequence metrics and segmentation."""

from decimal import Decimal

import pytest
from tests.unit.test_trade_outcomes import _evaluate

from ai_trading_team.evaluation import summarize_by, summarize_performance
from ai_trading_team.replay import ReplayError
from ai_trading_team.schemas.enums import (
    ResearchMetricStatus,
    SegmentDimension,
    TradeOutcomeStatus,
    TradeSide,
)
from ai_trading_team.schemas.evaluation import SegmentFacts, TradeOutcome


def _tp(side: TradeSide = TradeSide.BUY):  # type: ignore[no-untyped-def]
    if side is TradeSide.BUY:
        path = ((Decimal("1.08130"), Decimal("1.08165"), Decimal("1.08120"), Decimal("1.08150")),)
    else:
        path = ((Decimal("1.08130"), Decimal("1.08140"), Decimal("1.08095"), Decimal("1.08110")),)
    return _evaluate(path, side=side)


def _sl():  # type: ignore[no-untyped-def]
    return _as_loss(_tp())


def _as_loss(outcome: TradeOutcome, suffix: str = "loss") -> TradeOutcome:
    return TradeOutcome.model_validate(
        outcome.model_copy(
            update={
                "outcome_id": f"{outcome.outcome_id}-{suffix}",
                "status": TradeOutcomeStatus.STOP_LOSS_REACHED,
                "realized_r_multiple": Decimal("-1"),
            }
        ).model_dump()
    )


def test_metrics_are_decimal_and_sequence_drawdown_is_not_account_drawdown() -> None:
    win = _tp()
    summary = summarize_performance(
        (win, _as_loss(win, "loss-1"), _as_loss(win, "loss-2"))
    )
    assert summary.cumulative_r.value == Decimal("-0.5")
    assert summary.average_r.value == Decimal(
        "-0.16666666666666666666666666666666666666666666666667"
    )
    assert summary.sequence_max_drawdown_r.value == Decimal("2")
    assert isinstance(summary.win_rate.value, Decimal)


def test_profit_factor_without_losses_is_explicitly_unbounded() -> None:
    summary = summarize_performance((_tp(),))
    assert summary.profit_factor.status is ResearchMetricStatus.UNBOUNDED
    assert summary.profit_factor.value is None


def test_ambiguous_and_unresolved_do_not_enter_realized_metrics() -> None:
    ambiguous = _evaluate(
        ((Decimal("1.08130"), Decimal("1.08170"), Decimal("1.08100"), Decimal("1.08140")),)
    )
    unresolved = TradeOutcome.model_validate(
        ambiguous.model_copy(
            update={
                "outcome_id": f"{ambiguous.outcome_id}-unresolved",
                "status": TradeOutcomeStatus.UNRESOLVED_HORIZON,
                "resolution_candle_open_at": None,
                "resolution_candle_close_at": None,
                "bars_to_resolution": None,
                "seconds_to_resolution": None,
            }
        ).model_dump()
    )
    summary = summarize_performance((ambiguous, unresolved))
    assert summary.resolved_count == 0
    assert summary.average_r.status is ResearchMetricStatus.UNAVAILABLE
    assert summary.win_rate.status is ResearchMetricStatus.UNAVAILABLE


def test_segmentation_groups_only_recorded_pre_outcome_fact() -> None:
    buy = _tp()
    sell = TradeOutcome.model_validate(
        buy.model_copy(
            update={
                "outcome_id": f"{buy.outcome_id}-sell",
                "side": TradeSide.SELL,
                "stop_loss": Decimal("1.08150"),
                "take_profit": Decimal("1.08100"),
                "segment_facts": SegmentFacts(
                    direction=TradeSide.SELL,
                    timeframe=buy.segment_facts.timeframe,
                    partition=buy.partition_kind,
                ),
            }
        ).model_dump()
    )
    summaries = summarize_by((buy, sell), SegmentDimension.DIRECTION)
    assert tuple(item.value for item in summaries) == ("BUY", "SELL")


def test_metrics_repeat_byte_identically() -> None:
    from ai_trading_team.replay.serialization import canonical_replay_bytes

    win = _tp()
    outcomes = (win, _as_loss(win))
    first = summarize_performance(outcomes)
    second = summarize_performance(tuple(reversed(outcomes)))
    assert first == second
    assert canonical_replay_bytes(first) == canonical_replay_bytes(second)


def test_duplicate_outcome_identity_is_rejected() -> None:
    outcome = _tp()
    with pytest.raises(ReplayError, match="duplicate"):
        summarize_performance((outcome, outcome))
