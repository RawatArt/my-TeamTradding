"""Deterministic finite OHLC price-path outcome evaluation."""

from decimal import Context, Decimal, localcontext

from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.replay.identifiers import outcome_id
from ai_trading_team.replay.protocols import OutcomeDataView
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    OutcomeBasis,
    ReplayErrorCategory,
    TradeOutcomeStatus,
    TradeSide,
)
from ai_trading_team.schemas.evaluation import SegmentFacts, TradeOutcome
from ai_trading_team.schemas.replay import (
    FrozenReplayDecision,
    ReplayConfiguration,
    ReplayFrame,
)

_DECIMAL_CONTEXT = Context(prec=50)


class OutcomeEvaluator:
    """Evaluate one frozen trade hypothesis without fill or cost simulation."""

    evaluator_version = "1.0.0"

    def evaluate(
        self,
        frame: ReplayFrame,
        frozen: FrozenReplayDecision,
        view: OutcomeDataView,
        configuration: ReplayConfiguration,
        *,
        segment_facts: SegmentFacts | None = None,
    ) -> TradeOutcome:
        self._validate_links(frame, frozen, view, configuration)
        proposal = frozen.proposal
        if proposal.entry is None or proposal.stop_loss is None or proposal.take_profit is None:
            raise ReplayError(
                ReplayErrorCategory.INVALID_PROPOSAL,
                "outcome evaluation requires frozen entry, stop loss, and take profit",
            )
        entry = proposal.entry
        stop = proposal.stop_loss
        target = proposal.take_profit
        if proposal.side is TradeSide.BUY:
            valid_geometry = stop < entry < target
        else:
            valid_geometry = target < entry < stop
        if not valid_geometry:
            raise ReplayError(
                ReplayErrorCategory.INVALID_PROPOSAL,
                "frozen proposal has invalid directional geometry",
            )

        candles = view.candles
        previous_open = None
        for candle in candles:
            if (
                candle.symbol != frozen.symbol
                or candle.timeframe is not view.timeframe
                or candle.open_time < frozen.decision_cutoff
                or candle.close_time <= frozen.decision_cutoff
            ):
                raise ReplayError(
                    ReplayErrorCategory.FUTURE_DATA_ACCESS,
                    "outcome candle violates the strict post-decision boundary",
                )
            if previous_open is not None and candle.open_time <= previous_open:
                raise ReplayError(
                    ReplayErrorCategory.INVALID_OUTCOME_DATA,
                    "outcome candles must be strictly chronological",
                )
            previous_open = candle.open_time
        if configuration.outcome_horizon.max_bars is not None and len(candles) > (
            configuration.outcome_horizon.max_bars
        ):
            raise ReplayError(
                ReplayErrorCategory.INVALID_HORIZON,
                "outcome view exceeds its declared maximum-bar horizon",
            )
        if configuration.outcome_horizon.max_elapsed is not None and any(
            candle.close_time
            > frozen.decision_cutoff + configuration.outcome_horizon.max_elapsed
            for candle in candles
        ):
            raise ReplayError(
                ReplayErrorCategory.INVALID_HORIZON,
                "outcome view exceeds its declared elapsed-time horizon",
            )
        if any(candle.close_time > view.partition.evaluation_end for candle in candles):
            raise ReplayError(
                ReplayErrorCategory.PARTITION_VIOLATION,
                "outcome view crosses the partition evaluation end",
            )

        favorable = Decimal("0")
        adverse = Decimal("0")
        terminal_index = len(candles) - 1
        status = TradeOutcomeStatus.UNRESOLVED_HORIZON
        for index, candle in enumerate(candles):
            if proposal.side is TradeSide.BUY:
                favorable = max(favorable, candle.high - entry)
                adverse = max(adverse, entry - candle.low)
                tp_hit = candle.high >= target
                sl_hit = candle.low <= stop
            else:
                favorable = max(favorable, entry - candle.low)
                adverse = max(adverse, candle.high - entry)
                tp_hit = candle.low <= target
                sl_hit = candle.high >= stop
            if tp_hit and sl_hit:
                status = TradeOutcomeStatus.AMBIGUOUS_INTRABAR
            elif tp_hit:
                status = TradeOutcomeStatus.TAKE_PROFIT_REACHED
            elif sl_hit:
                status = TradeOutcomeStatus.STOP_LOSS_REACHED
            else:
                continue
            terminal_index = index
            break

        evaluated = candles[: terminal_index + 1]
        terminal = evaluated[-1]
        risk_unit = abs(entry - stop)
        with localcontext(_DECIMAL_CONTEXT):
            mfe_r = favorable / risk_unit
            mae_r = adverse / risk_unit
            realized = (
                abs(target - entry) / risk_unit
                if status is TradeOutcomeStatus.TAKE_PROFIT_REACHED
                else Decimal("-1")
                if status is TradeOutcomeStatus.STOP_LOSS_REACHED
                else None
            )
        has_terminal_event = status is not TradeOutcomeStatus.UNRESOLVED_HORIZON
        elapsed = terminal.close_time - frozen.decision_cutoff
        seconds = Decimal(
            elapsed.days * 86_400_000_000
            + elapsed.seconds * 1_000_000
            + elapsed.microseconds
        ) / Decimal("1000000")
        policy_hash = content_digest(
            {
                "evaluation_policy_version": configuration.evaluation_policy_version,
                "outcome_timeframe": configuration.outcome_timeframe,
                "horizon": configuration.outcome_horizon,
                "entry_policy": configuration.entry_policy,
                "intrabar_policy": configuration.intrabar_policy,
                "outcome_basis": configuration.outcome_basis,
            }
        )
        facts = segment_facts or SegmentFacts(
            direction=proposal.side,
            timeframe=frame.primary_timeframe,
            partition=frame.partition_kind,
        )
        if (
            facts.direction is not proposal.side
            or facts.timeframe is not frame.primary_timeframe
            or facts.partition is not frame.partition_kind
        ):
            raise ReplayError(
                ReplayErrorCategory.INVALID_OUTCOME_DATA,
                "segment facts must be frozen decision-time facts",
            )
        return TradeOutcome(
            evaluator_version=self.evaluator_version,
            outcome_id=outcome_id(frame.frame_id, frozen.proposal_digest, policy_hash),
            replay_id=frame.replay_id,
            frame_id=frame.frame_id,
            cycle_id=frame.cycle_id,
            snapshot_id=frame.snapshot_id,
            proposal_id=proposal.proposal_id,
            proposal_digest=frozen.proposal_digest,
            dataset_id=frame.dataset_id,
            dataset_digest=frame.dataset_digest,
            partition_id=frame.partition_id,
            partition_kind=frame.partition_kind,
            symbol=frame.symbol,
            side=proposal.side,
            timeframe=view.timeframe,
            decision_cutoff=frozen.decision_cutoff,
            evaluation_started_at=evaluated[0].open_time,
            evaluation_ended_at=terminal.close_time,
            horizon=configuration.outcome_horizon,
            bars_evaluated=len(evaluated),
            status=status,
            resolution_candle_open_at=terminal.open_time if has_terminal_event else None,
            resolution_candle_close_at=terminal.close_time if has_terminal_event else None,
            bars_to_resolution=len(evaluated) if has_terminal_event else None,
            seconds_to_resolution=seconds if has_terminal_event else None,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            risk_unit=risk_unit,
            realized_r_multiple=realized,
            maximum_favorable_excursion=favorable,
            maximum_adverse_excursion=adverse,
            mfe_r=mfe_r,
            mae_r=mae_r,
            outcome_candle_digest=content_digest(evaluated),
            evaluation_policy_digest=policy_hash,
            outcome_basis=OutcomeBasis.THEORETICAL_LEVEL_TOUCH_NO_COSTS,
            segment_facts=facts,
        )

    @staticmethod
    def _validate_links(
        frame: ReplayFrame,
        frozen: FrozenReplayDecision,
        view: OutcomeDataView,
        configuration: ReplayConfiguration,
    ) -> None:
        if (
            frozen.replay_id != frame.replay_id
            or frozen.frame_id != frame.frame_id
            or frozen.cycle_id != frame.cycle_id
            or frozen.snapshot_id != frame.snapshot_id
            or frozen.symbol != frame.symbol
            or view.decision_cutoff != frame.decision_cutoff
            or view.partition.partition_id != frame.partition_id
            or view.dataset_digest != frame.dataset_digest
            or configuration.dataset_digest != frame.dataset_digest
            or configuration.outcome_timeframe is not view.timeframe
        ):
            raise ReplayError(
                ReplayErrorCategory.DECISION_NOT_FROZEN,
                "outcome inputs do not share one frozen replay identity",
            )
