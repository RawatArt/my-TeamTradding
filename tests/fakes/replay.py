"""Deterministic M8 historical replay fixtures without MT5 or providers."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.config import (
    FeatureEngineSettings,
    MarketDataSettings,
    RiskConstitutionSettings,
)
from ai_trading_team.features.serialization import configuration_digest
from ai_trading_team.replay.engine import HistoricalReplayEngine, freeze_replay_decision
from ai_trading_team.replay.serialization import dataset_digest
from ai_trading_team.replay.source import InMemoryHistoricalMarketDataSource
from ai_trading_team.risk import RiskEngine, account_fingerprint
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    ReplayDecisionSource,
    Timeframe,
    TradeSide,
)
from ai_trading_team.schemas.historical import (
    DatasetPartition,
    HistoricalCandle,
    HistoricalDataset,
    HistoricalDatasetMetadata,
    HistoricalSnapshotObservations,
)
from ai_trading_team.schemas.replay import (
    FrozenReplayDecision,
    OutcomeHorizon,
    ReplayBuildResult,
    ReplayConfiguration,
)
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision
from ai_trading_team.schemas.timeframes import timeframe_duration
from tests.fakes.market import SYMBOL, account_info, symbol_info, tick

REPLAY_CUTOFF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
PARTITION_ID = "research-2026-q3"


def historical_candle(
    timeframe: Timeframe,
    open_time: datetime,
    *,
    index: int,
    open_price: Decimal = Decimal("1.08130"),
    high: Decimal = Decimal("1.08140"),
    low: Decimal = Decimal("1.08120"),
    close: Decimal = Decimal("1.08130"),
) -> HistoricalCandle:
    return HistoricalCandle(
        source_record_id=f"{timeframe.value.lower()}-{index:05d}",
        symbol=SYMBOL,
        timeframe=timeframe,
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        tick_volume=100 + index,
        broker_spread_points=12,
        real_volume=index,
    )


def replay_dataset(
    *,
    future_m15: tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...] | None = None,
) -> HistoricalDataset:
    future = future_m15 or (
        (
            Decimal("1.08130"),
            Decimal("1.08170"),
            Decimal("1.08120"),
            Decimal("1.08160"),
        ),
        (
            Decimal("1.08160"),
            Decimal("1.08200"),
            Decimal("1.08150"),
            Decimal("1.08190"),
        ),
    )
    partition = DatasetPartition(
        partition_id=PARTITION_ID,
        kind=DatasetPartitionKind.RESEARCH,
        context_start=REPLAY_CUTOFF - timedelta(days=40),
        evaluation_start=REPLAY_CUTOFF,
        evaluation_end=REPLAY_CUTOFF + timedelta(days=2),
    )
    metadata = HistoricalDatasetMetadata(
        dataset_id="fixture-eurusd-2026",
        dataset_version="1.0.0",
        source_ref="deterministic-test-fixture",
        symbols=(SYMBOL,),
        timeframes=(Timeframe.H1, Timeframe.H4, Timeframe.M15),
        partitions=(partition,),
    )
    candles: list[HistoricalCandle] = []
    for timeframe in metadata.timeframes:
        duration = timeframe_duration(timeframe)
        first = REPLAY_CUTOFF - duration * 205
        for index in range(205):
            offset = Decimal(index % 7) * Decimal("0.00001")
            base = Decimal("1.08130") + offset
            candles.append(
                historical_candle(
                    timeframe,
                    first + duration * index,
                    index=index,
                    open_price=base,
                    high=base + Decimal("0.00010"),
                    low=base - Decimal("0.00010"),
                    close=base + Decimal("0.00002"),
                )
            )
        if timeframe is Timeframe.M15:
            for future_index, values in enumerate(future, start=205):
                candles.append(
                    historical_candle(
                        timeframe,
                        REPLAY_CUTOFF + duration * (future_index - 205),
                        index=future_index,
                        open_price=values[0],
                        high=values[1],
                        low=values[2],
                        close=values[3],
                    )
                )
    candles.sort(
        key=lambda item: (
            item.symbol,
            item.timeframe.value,
            item.open_time,
            item.source_record_id,
        )
    )
    observations = HistoricalSnapshotObservations(
        observation_id="snapshot-observation-001",
        effective_at=REPLAY_CUTOFF,
        symbol=SYMBOL,
        symbol_info=symbol_info().model_copy(
            update={"retrieved_at": REPLAY_CUTOFF - timedelta(seconds=1)}
        ),
        tick=tick(source_time=REPLAY_CUTOFF - timedelta(seconds=1)).model_copy(
            update={"retrieved_at": REPLAY_CUTOFF - timedelta(seconds=1)}
        ),
        account=account_info(retrieved_at=REPLAY_CUTOFF - timedelta(seconds=1)),
    )
    unsealed = HistoricalDataset(
        metadata=metadata,
        dataset_digest="sha256:" + "0" * 64,
        candles=tuple(candles),
        snapshot_observations=(observations,),
    )
    return HistoricalDataset.model_validate(
        unsealed.model_copy(
            update={"dataset_digest": dataset_digest(unsealed)}
        ).model_dump()
    )


def replay_configuration(
    dataset: HistoricalDataset,
    *,
    max_bars: int = 2,
) -> ReplayConfiguration:
    return ReplayConfiguration(
        dataset_id=dataset.metadata.dataset_id,
        dataset_digest=dataset.dataset_digest,
        partition_id=PARTITION_ID,
        symbol=SYMBOL,
        replay_schedule=(REPLAY_CUTOFF,),
        feature_configuration_digest=configuration_digest(FeatureEngineSettings()),
        outcome_horizon=OutcomeHorizon(max_bars=max_bars),
    )


def replay_build(
    dataset: HistoricalDataset | None = None,
) -> tuple[
    HistoricalDataset,
    InMemoryHistoricalMarketDataSource,
    ReplayConfiguration,
    ReplayBuildResult,
]:
    selected = dataset or replay_dataset()
    source = InMemoryHistoricalMarketDataSource(selected)
    configuration = replay_configuration(selected)
    result = HistoricalReplayEngine(
        source,
        MarketDataSettings(),
        FeatureEngineSettings(),
    ).build_frame(configuration, REPLAY_CUTOFF)
    return selected, source, configuration, result


def replay_proposal(
    result: ReplayBuildResult,
    *,
    side: TradeSide = TradeSide.BUY,
    entry: Decimal = Decimal("1.08130"),
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> TradeProposal:
    stop = stop_loss or (
        Decimal("1.08110") if side is TradeSide.BUY else Decimal("1.08150")
    )
    target = take_profit or (
        Decimal("1.08160") if side is TradeSide.BUY else Decimal("1.08100")
    )
    return TradeProposal(
        cycle_id=result.frame.cycle_id,
        snapshot_id=result.frame.snapshot_id,
        timestamp=REPLAY_CUTOFF,
        proposal_id="replay-proposal-001",
        symbol=SYMBOL,
        side=side,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        rationale="Scripted deterministic replay proposal",
    )


def frozen_decision(result: ReplayBuildResult) -> FrozenReplayDecision:
    return freeze_replay_decision(
        result.frame,
        replay_proposal(result),
        source=ReplayDecisionSource.SCRIPTED,
        frozen_at=REPLAY_CUTOFF,
    )


def replay_risk_decision(
    result: ReplayBuildResult, proposal: TradeProposal | None = None
) -> RiskDecision:
    """Build an unchanged M3 decision from genuine fixture as-of account context."""
    selected = proposal or replay_proposal(result)
    snapshot = result.snapshot
    context = AccountRiskContext(
        cycle_id=snapshot.cycle_id,
        snapshot_id=snapshot.snapshot_id,
        account_ref=account_fingerprint(snapshot.account.account_id, snapshot.account.server),
        context_as_of=REPLAY_CUTOFF,
        trading_day_started_at=REPLAY_CUTOFF - timedelta(hours=12),
        cash_flow_adjusted_peak_equity=snapshot.account.equity,
        adjusted_day_start_equity=snapshot.account.equity,
        account_open_position_count=0,
    )
    return RiskEngine(RiskConstitutionSettings()).evaluate(
        selected, snapshot, context, REPLAY_CUTOFF
    )
