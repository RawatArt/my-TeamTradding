"""Known-path M8 TradeOutcome tests."""

from decimal import Decimal

from tests.fakes.replay import (
    PARTITION_ID,
    frozen_decision,
    replay_build,
    replay_configuration,
    replay_dataset,
    replay_proposal,
)

from ai_trading_team.evaluation import OutcomeEvaluator
from ai_trading_team.schemas.enums import Timeframe, TradeOutcomeStatus, TradeSide
from ai_trading_team.schemas.evaluation import TradeOutcome
from ai_trading_team.schemas.historical import HistoricalDataset


def _evaluate(
    future: tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...],
    *,
    side: TradeSide = TradeSide.BUY,
    max_bars: int | None = None,
    dataset_override: HistoricalDataset | None = None,
) -> TradeOutcome:
    dataset = dataset_override or replay_dataset(future_m15=future)
    _, source, _, result = replay_build(dataset)
    configuration = replay_configuration(dataset, max_bars=max_bars or len(future))
    proposal = replay_proposal(result, side=side)
    from ai_trading_team.replay.engine import freeze_replay_decision
    from ai_trading_team.schemas.enums import ReplayDecisionSource

    frozen = freeze_replay_decision(
        result.frame,
        proposal,
        source=ReplayDecisionSource.SCRIPTED,
        frozen_at=result.frame.decision_cutoff,
    )
    view = source.outcome_view(
        frozen, PARTITION_ID, Timeframe.M15, configuration.outcome_horizon
    )
    return OutcomeEvaluator().evaluate(result.frame, frozen, view, configuration)


def test_take_profit_only_resolves_buy() -> None:
    outcome = _evaluate(
        ((Decimal("1.08130"), Decimal("1.08165"), Decimal("1.08120"), Decimal("1.08150")),)
    )
    assert outcome.status is TradeOutcomeStatus.TAKE_PROFIT_REACHED
    assert outcome.realized_r_multiple == Decimal("1.5")
    assert outcome.bars_to_resolution == 1


def test_stop_loss_only_resolves_buy() -> None:
    outcome = _evaluate(
        ((Decimal("1.08130"), Decimal("1.08140"), Decimal("1.08105"), Decimal("1.08110")),)
    )
    assert outcome.status is TradeOutcomeStatus.STOP_LOSS_REACHED
    assert outcome.realized_r_multiple == Decimal("-1")


def test_neither_hit_expires_at_finite_horizon() -> None:
    quiet = (
        (Decimal("1.08130"), Decimal("1.08140"), Decimal("1.08120"), Decimal("1.08131")),
        (Decimal("1.08131"), Decimal("1.08145"), Decimal("1.08125"), Decimal("1.08135")),
    )
    outcome = _evaluate(quiet)
    assert outcome.status is TradeOutcomeStatus.UNRESOLVED_HORIZON
    assert outcome.bars_evaluated == 2
    assert outcome.realized_r_multiple is None


def test_same_bar_tp_and_sl_is_explicitly_ambiguous() -> None:
    outcome = _evaluate(
        ((Decimal("1.08130"), Decimal("1.08170"), Decimal("1.08100"), Decimal("1.08140")),)
    )
    assert outcome.status is TradeOutcomeStatus.AMBIGUOUS_INTRABAR
    assert outcome.realized_r_multiple is None


def test_buy_and_sell_paths_are_directionally_symmetric() -> None:
    buy = _evaluate(
        ((Decimal("1.08130"), Decimal("1.08165"), Decimal("1.08120"), Decimal("1.08150")),)
    )
    sell = _evaluate(
        (
            (
                Decimal("1.08130"),
                Decimal("1.08140"),
                Decimal("1.08095"),
                Decimal("1.08110"),
            ),
        ),
        side=TradeSide.SELL,
    )
    assert buy.status is sell.status is TradeOutcomeStatus.TAKE_PROFIT_REACHED
    assert buy.realized_r_multiple == sell.realized_r_multiple == Decimal("1.5")


def test_mfe_mae_stop_at_resolution_candle() -> None:
    outcome = _evaluate(
        (
            (Decimal("1.08130"), Decimal("1.08165"), Decimal("1.08120"), Decimal("1.08150")),
            (Decimal("1.08150"), Decimal("1.09000"), Decimal("1.07000"), Decimal("1.08000")),
        )
    )
    assert outcome.bars_evaluated == 1
    assert outcome.maximum_favorable_excursion == Decimal("0.00035")
    assert outcome.maximum_adverse_excursion == Decimal("0.00010")


def test_decision_candle_cannot_resolve_or_affect_excursions() -> None:
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
    modified = tuple(
        candle.model_copy(
            update={"high": Decimal("1.09000"), "low": Decimal("1.07000")}
        )
        if candle.timeframe is Timeframe.M15
        and candle.close_time == dataset.metadata.partitions[0].evaluation_start
        else candle
        for candle in dataset.candles
    )
    from ai_trading_team.replay.serialization import dataset_digest

    changed = dataset.model_copy(update={"candles": modified})
    changed = changed.model_copy(update={"dataset_digest": dataset_digest(changed)})
    outcome = _evaluate(
        (
            (
                Decimal("1.08130"),
                Decimal("1.08140"),
                Decimal("1.08120"),
                Decimal("1.08130"),
            ),
        ),
        dataset_override=changed,
    )
    assert changed.candles != dataset.candles
    assert outcome.status is TradeOutcomeStatus.UNRESOLVED_HORIZON
    assert outcome.maximum_favorable_excursion == Decimal("0.00010")
    assert outcome.maximum_adverse_excursion == Decimal("0.00010")


def test_ambiguity_candle_is_the_terminal_excursion_candle() -> None:
    outcome = _evaluate(
        (
            (Decimal("1.08130"), Decimal("1.08170"), Decimal("1.08100"), Decimal("1.08140")),
            (Decimal("1.08140"), Decimal("1.10000"), Decimal("1.00000"), Decimal("1.05000")),
        )
    )
    assert outcome.status is TradeOutcomeStatus.AMBIGUOUS_INTRABAR
    assert outcome.bars_evaluated == 1
    assert outcome.maximum_favorable_excursion == Decimal("0.00040")


def test_helper_frozen_decision_remains_usable() -> None:
    _, source, configuration, result = replay_build()
    frozen = frozen_decision(result)
    view = source.outcome_view(
        frozen, PARTITION_ID, Timeframe.M15, configuration.outcome_horizon
    )
    assert OutcomeEvaluator().evaluate(result.frame, frozen, view, configuration)
