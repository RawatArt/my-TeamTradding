"""Capability-separated M8 historical source interfaces."""

from datetime import datetime
from typing import Protocol

from ai_trading_team.schemas.enums import Timeframe
from ai_trading_team.schemas.historical import (
    DatasetPartition,
    HistoricalCandle,
    HistoricalDatasetMetadata,
    HistoricalSnapshotObservations,
)
from ai_trading_team.schemas.replay import FrozenReplayDecision, OutcomeHorizon


class DecisionDataView(Protocol):
    """Cutoff-capped interface with deliberately no future-data operation."""

    @property
    def metadata(self) -> HistoricalDatasetMetadata: ...

    @property
    def dataset_digest(self) -> str: ...

    @property
    def partition(self) -> DatasetPartition: ...

    @property
    def decision_cutoff(self) -> datetime: ...

    def completed_candles(
        self, symbol: str, timeframe: Timeframe, count: int
    ) -> tuple[HistoricalCandle, ...]: ...

    def snapshot_observations(self, symbol: str) -> HistoricalSnapshotObservations: ...


class OutcomeDataView(Protocol):
    """Finite post-decision candle capability issued after decision freezing."""

    @property
    def partition(self) -> DatasetPartition: ...

    @property
    def dataset_digest(self) -> str: ...

    @property
    def decision_cutoff(self) -> datetime: ...

    @property
    def timeframe(self) -> Timeframe: ...

    @property
    def candles(self) -> tuple[HistoricalCandle, ...]: ...


class HistoricalMarketDataSource(Protocol):
    """Storage-neutral source that issues narrow decision/outcome capabilities."""

    @property
    def metadata(self) -> HistoricalDatasetMetadata: ...

    @property
    def dataset_digest(self) -> str: ...

    def decision_view(self, partition_id: str, cutoff: datetime) -> DecisionDataView: ...

    def outcome_view(
        self,
        frozen: FrozenReplayDecision,
        partition_id: str,
        timeframe: Timeframe,
        horizon: OutcomeHorizon,
    ) -> OutcomeDataView: ...
