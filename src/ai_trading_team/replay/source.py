"""In-memory and file-backed deterministic historical sources."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.replay.serialization import dataset_digest
from ai_trading_team.schemas.enums import ReplayErrorCategory, Timeframe
from ai_trading_team.schemas.historical import (
    DatasetPartition,
    HistoricalCandle,
    HistoricalDataset,
    HistoricalDatasetMetadata,
    HistoricalSnapshotObservations,
)
from ai_trading_team.schemas.replay import FrozenReplayDecision, OutcomeHorizon


class _DecisionView:
    def __init__(
        self,
        dataset: HistoricalDataset,
        partition: DatasetPartition,
        cutoff: datetime,
    ) -> None:
        self._dataset = dataset
        self._partition = partition
        self._cutoff = cutoff

    @property
    def metadata(self) -> HistoricalDatasetMetadata:
        return self._dataset.metadata

    @property
    def dataset_digest(self) -> str:
        return self._dataset.dataset_digest

    @property
    def partition(self) -> DatasetPartition:
        return self._partition

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff

    def completed_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> tuple[HistoricalCandle, ...]:
        if count <= 0 or count > 5_000:
            raise ReplayError(
                ReplayErrorCategory.INVALID_DATASET,
                "decision candle count must be between 1 and 5000",
            )
        candles = tuple(
            candle
            for candle in self._dataset.candles
            if candle.symbol == symbol
            and candle.timeframe is timeframe
            and candle.open_time >= self._partition.context_start
            and candle.close_time <= self._cutoff
        )
        return candles[-count:]

    def snapshot_observations(self, symbol: str) -> HistoricalSnapshotObservations:
        candidates = tuple(
            item
            for item in self._dataset.snapshot_observations
            if item.symbol == symbol
            and item.effective_at >= self._partition.context_start
            and item.effective_at <= self._cutoff
        )
        if not candidates:
            raise ReplayError(
                ReplayErrorCategory.MISSING_AS_OF_OBSERVATION,
                "snapshot-capable as-of observations are unavailable",
            )
        return candidates[-1]


class _OutcomeView:
    def __init__(
        self,
        dataset_digest: str,
        partition: DatasetPartition,
        cutoff: datetime,
        timeframe: Timeframe,
        candles: tuple[HistoricalCandle, ...],
    ) -> None:
        self._dataset_digest = dataset_digest
        self._partition = partition
        self._cutoff = cutoff
        self._timeframe = timeframe
        self._candles = candles

    @property
    def partition(self) -> DatasetPartition:
        return self._partition

    @property
    def dataset_digest(self) -> str:
        return self._dataset_digest

    @property
    def decision_cutoff(self) -> datetime:
        return self._cutoff

    @property
    def timeframe(self) -> Timeframe:
        return self._timeframe

    @property
    def candles(self) -> tuple[HistoricalCandle, ...]:
        return self._candles


class InMemoryHistoricalMarketDataSource:
    """Validated source used by fixtures and by the file adapter after parsing."""

    def __init__(self, dataset: HistoricalDataset) -> None:
        calculated = dataset_digest(dataset)
        if calculated != dataset.dataset_digest:
            raise ReplayError(
                ReplayErrorCategory.DATASET_DIGEST_MISMATCH,
                "historical dataset digest does not match canonical contents",
            )
        self._dataset = dataset

    @property
    def metadata(self) -> HistoricalDatasetMetadata:
        return self._dataset.metadata

    @property
    def dataset_digest(self) -> str:
        return self._dataset.dataset_digest

    def decision_view(self, partition_id: str, cutoff: datetime) -> _DecisionView:
        moment = _utc(cutoff)
        partition = self._partition(partition_id)
        if moment < partition.evaluation_start or moment >= partition.evaluation_end:
            raise ReplayError(
                ReplayErrorCategory.PARTITION_VIOLATION,
                "decision cutoff is outside the partition evaluation range",
            )
        return _DecisionView(self._dataset, partition, moment)

    def outcome_view(
        self,
        frozen: FrozenReplayDecision,
        partition_id: str,
        timeframe: Timeframe,
        horizon: OutcomeHorizon,
    ) -> _OutcomeView:
        partition = self._partition(partition_id)
        cutoff = frozen.decision_cutoff
        if cutoff < partition.evaluation_start or cutoff >= partition.evaluation_end:
            raise ReplayError(
                ReplayErrorCategory.PARTITION_VIOLATION,
                "frozen decision cutoff is outside the partition evaluation range",
            )
        candidates = tuple(
            candle
            for candle in self._dataset.candles
            if candle.symbol == frozen.symbol
            and candle.timeframe is timeframe
            and candle.open_time >= cutoff
            and candle.close_time > cutoff
            and candle.close_time <= partition.evaluation_end
        )
        if horizon.max_bars is not None:
            selected = candidates[: horizon.max_bars]
        else:
            if horizon.max_elapsed is None:
                raise ReplayError(ReplayErrorCategory.INVALID_HORIZON, "finite horizon missing")
            horizon_end = min(cutoff + horizon.max_elapsed, partition.evaluation_end)
            selected = tuple(candle for candle in candidates if candle.close_time <= horizon_end)
        if not selected:
            raise ReplayError(
                ReplayErrorCategory.INVALID_OUTCOME_DATA,
                "no completed post-decision candles exist inside the finite horizon",
            )
        return _OutcomeView(self.dataset_digest, partition, cutoff, timeframe, selected)

    def _partition(self, partition_id: str) -> DatasetPartition:
        for partition in self._dataset.metadata.partitions:
            if partition.partition_id == partition_id:
                return partition
        raise ReplayError(
            ReplayErrorCategory.PARTITION_VIOLATION,
            "requested partition is not declared by the dataset",
        )


class FileHistoricalMarketDataSource(InMemoryHistoricalMarketDataSource):
    """Local UTF-8 JSON dataset adapter with no download or network behavior."""

    def __init__(self, path: Path | str) -> None:
        dataset = HistoricalDataset.model_validate_json(Path(path).read_text(encoding="utf-8"))
        super().__init__(dataset)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayError(
            ReplayErrorCategory.INVALID_REPLAY_CLOCK,
            "replay cutoff must be timezone-aware",
        )
    return value.astimezone(UTC)
