"""Deterministic aggregate R-based research metrics."""

from decimal import Context, Decimal, localcontext

from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    ReplayErrorCategory,
    ResearchMetricStatus,
    TradeOutcomeStatus,
)
from ai_trading_team.schemas.evaluation import (
    PerformanceSummary,
    ResearchMetric,
    TradeOutcome,
)

_CONTEXT = Context(prec=50)


def summarize_performance(outcomes: tuple[TradeOutcome, ...]) -> PerformanceSummary:
    """Summarize one replay/partition without synthesizing an equity curve."""
    if not outcomes:
        raise ReplayError(
            ReplayErrorCategory.INVALID_OUTCOME_DATA,
            "performance summary requires at least one outcome",
        )
    ordered = tuple(sorted(outcomes, key=lambda item: (item.decision_cutoff, item.outcome_id)))
    if len({item.outcome_id for item in ordered}) != len(ordered):
        raise ReplayError(
            ReplayErrorCategory.INVALID_OUTCOME_DATA,
            "performance summary cannot contain duplicate outcome identities",
        )
    first = ordered[0]
    if any(
        item.replay_id != first.replay_id
        or item.dataset_digest != first.dataset_digest
        or item.partition_id != first.partition_id
        or item.partition_kind is not first.partition_kind
        for item in ordered
    ):
        raise ReplayError(
            ReplayErrorCategory.PARTITION_VIOLATION,
            "performance outcomes must belong to one replay partition",
        )
    wins = tuple(
        item for item in ordered if item.status is TradeOutcomeStatus.TAKE_PROFIT_REACHED
    )
    losses = tuple(
        item for item in ordered if item.status is TradeOutcomeStatus.STOP_LOSS_REACHED
    )
    resolved = wins + losses
    realized = tuple(
        item.realized_r_multiple
        for item in ordered
        if item.realized_r_multiple is not None
    )
    unresolved_count = sum(
        item.status is TradeOutcomeStatus.UNRESOLVED_HORIZON for item in ordered
    )
    ambiguous_count = sum(
        item.status is TradeOutcomeStatus.AMBIGUOUS_INTRABAR for item in ordered
    )
    with localcontext(_CONTEXT):
        cumulative = sum(realized, Decimal("0"))
        average = cumulative / Decimal(len(realized)) if realized else None
        median = _median(realized)
        win_rate = Decimal(len(wins)) / Decimal(len(resolved)) if resolved else None
        gross_win = sum(
            (value for value in realized if value > 0), Decimal("0")
        )
        gross_loss = abs(sum((value for value in realized if value < 0), Decimal("0")))
        if gross_loss > 0:
            profit_factor = _valid(gross_win / gross_loss)
        elif gross_win > 0:
            profit_factor = ResearchMetric(status=ResearchMetricStatus.UNBOUNDED)
        else:
            profit_factor = _unavailable()
        drawdown = _sequence_max_drawdown(realized) if realized else None
        holding_bars = (
            sum(Decimal(item.bars_to_resolution or 0) for item in resolved)
            / Decimal(len(resolved))
            if resolved
            else None
        )
        holding_seconds = (
            sum((item.seconds_to_resolution or Decimal("0") for item in resolved), Decimal("0"))
            / Decimal(len(resolved))
            if resolved
            else None
        )
        average_mfe = sum((item.mfe_r for item in ordered), Decimal("0")) / Decimal(len(ordered))
        average_mae = sum((item.mae_r for item in ordered), Decimal("0")) / Decimal(len(ordered))
    outcome_hash = content_digest(ordered)
    return PerformanceSummary(
        summary_id=deterministic_id(
            "summary",
            {
                "replay_id": first.replay_id,
                "partition_id": first.partition_id,
                "outcome_digest": outcome_hash,
            },
        ),
        replay_id=first.replay_id,
        dataset_digest=first.dataset_digest,
        partition_id=first.partition_id,
        partition_kind=first.partition_kind,
        outcome_count=len(ordered),
        resolved_count=len(resolved),
        unresolved_count=unresolved_count,
        ambiguous_count=ambiguous_count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=_optional(win_rate),
        cumulative_r=_optional(cumulative if realized else None),
        average_r=_optional(average),
        median_r=_optional(median),
        expectancy_r=_optional(average),
        profit_factor=profit_factor,
        sequence_max_drawdown_r=_optional(drawdown),
        average_holding_bars=_optional(holding_bars),
        average_holding_seconds=_optional(holding_seconds),
        average_mfe_r=_valid(average_mfe),
        average_mae_r=_valid(average_mae),
        outcome_digest=outcome_hash,
        generated_at=max(item.evaluation_ended_at for item in ordered),
    )


def _median(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _sequence_max_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    running = Decimal("0")
    peak = Decimal("0")
    maximum = Decimal("0")
    for value in values:
        running += value
        peak = max(peak, running)
        maximum = max(maximum, peak - running)
    return maximum


def _valid(value: Decimal) -> ResearchMetric:
    return ResearchMetric(status=ResearchMetricStatus.VALID, value=value)


def _unavailable() -> ResearchMetric:
    return ResearchMetric(status=ResearchMetricStatus.UNAVAILABLE)


def _optional(value: Decimal | None) -> ResearchMetric:
    return _unavailable() if value is None else _valid(value)
