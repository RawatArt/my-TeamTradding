"""Descriptive grouping by immutable pre-outcome facts only."""

from collections import defaultdict

from ai_trading_team.evaluation.metrics import summarize_performance
from ai_trading_team.schemas.enums import SegmentDimension
from ai_trading_team.schemas.evaluation import SegmentedPerformanceSummary, TradeOutcome


def summarize_by(
    outcomes: tuple[TradeOutcome, ...], dimension: SegmentDimension
) -> tuple[SegmentedPerformanceSummary, ...]:
    """Group by one predeclared fact; never rank or select a winning segment."""
    grouped: dict[str, list[TradeOutcome]] = defaultdict(list)
    for outcome in outcomes:
        value = _segment_value(outcome, dimension)
        if value is not None:
            grouped[value].append(outcome)
    return tuple(
        SegmentedPerformanceSummary(
            dimension=dimension,
            value=value,
            summary=summarize_performance(tuple(grouped[value])),
        )
        for value in sorted(grouped)
    )


def _segment_value(outcome: TradeOutcome, dimension: SegmentDimension) -> str | None:
    facts = outcome.segment_facts
    mapping = {
        SegmentDimension.DIRECTION: facts.direction.value,
        SegmentDimension.TIMEFRAME: facts.timeframe.value,
        SegmentDimension.PARTITION: facts.partition.value,
        SegmentDimension.FEATURE_REGIME: facts.feature_regime,
        SegmentDimension.VOLATILITY_BUCKET: facts.volatility_bucket,
        SegmentDimension.TREND_STRENGTH_BUCKET: facts.trend_strength_bucket,
        SegmentDimension.CHIEF_DECISION: facts.chief_decision,
        SegmentDimension.SKEPTIC_DECISION: facts.skeptic_decision,
    }
    return mapping[dimension]
