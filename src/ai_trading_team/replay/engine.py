"""Deterministic decision-world replay composition and freeze gate."""

from datetime import datetime

from pydantic import ValidationError

from ai_trading_team.config.settings import FeatureEngineSettings, MarketDataSettings
from ai_trading_team.features.engine import MarketFeatureEngine
from ai_trading_team.features.serialization import configuration_digest
from ai_trading_team.replay.errors import ReplayError
from ai_trading_team.replay.identifiers import (
    cycle_id,
    deterministic_id,
    frame_id,
    replay_id,
    snapshot_id,
)
from ai_trading_team.replay.protocols import HistoricalMarketDataSource
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.replay.snapshot import HistoricalSnapshotBuilder
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import ReplayDecisionSource, ReplayErrorCategory
from ai_trading_team.schemas.replay import (
    ArtifactReference,
    FrozenReplayDecision,
    PersistedRiskDecisionLink,
    ReplayBuildResult,
    ReplayConfiguration,
    ReplayFrame,
)
from ai_trading_team.schemas.risk import RiskDecision


class HistoricalReplayEngine:
    """Build decision artifacts only; this class has no outcome-source capability."""

    def __init__(
        self,
        source: HistoricalMarketDataSource,
        market_settings: MarketDataSettings,
        feature_settings: FeatureEngineSettings,
    ) -> None:
        self._source = source
        self._snapshot_builder = HistoricalSnapshotBuilder(market_settings)
        self._feature_engine = MarketFeatureEngine(feature_settings)
        self._feature_settings = feature_settings

    def build_frame(
        self, configuration: ReplayConfiguration, replay_time: datetime
    ) -> ReplayBuildResult:
        if replay_time not in configuration.replay_schedule:
            raise ReplayError(
                ReplayErrorCategory.INVALID_REPLAY_CLOCK,
                "replay time is not present in the declared deterministic schedule",
            )
        if (
            configuration.dataset_id != self._source.metadata.dataset_id
            or configuration.dataset_digest != self._source.dataset_digest
        ):
            raise ReplayError(
                ReplayErrorCategory.DATASET_DIGEST_MISMATCH,
                "replay configuration does not match its historical dataset",
            )
        expected_feature_digest = configuration_digest(self._feature_settings)
        if configuration.feature_configuration_digest != expected_feature_digest:
            raise ReplayError(
                ReplayErrorCategory.FEATURE_REPRODUCTION_FAILURE,
                "replay feature configuration digest is incompatible",
            )
        configuration_hash = content_digest(configuration)
        replay_identity = replay_id(configuration_hash)
        frame_identity = frame_id(
            replay_identity,
            configuration.symbol,
            configuration.primary_timeframe.value,
            replay_time,
        )
        cycle_identity = cycle_id(frame_identity)
        snapshot_identity = snapshot_id(frame_identity)
        view = self._source.decision_view(configuration.partition_id, replay_time)
        snapshot = self._snapshot_builder.build(
            view,
            cycle_id=cycle_identity,
            snapshot_id=snapshot_identity,
            symbol=configuration.symbol,
            primary_timeframe=configuration.primary_timeframe,
        )
        try:
            features = self._feature_engine.calculate(snapshot)
        except Exception as exc:
            raise ReplayError(
                ReplayErrorCategory.FEATURE_REPRODUCTION_FAILURE,
                "M7 feature calculation failed for historical snapshot",
            ) from exc
        snapshot_hash = content_digest(snapshot)
        features_hash = content_digest(features)
        frame = ReplayFrame(
            replay_id=replay_identity,
            frame_id=frame_identity,
            dataset_id=configuration.dataset_id,
            dataset_digest=configuration.dataset_digest,
            partition_id=view.partition.partition_id,
            partition_kind=view.partition.kind,
            cycle_id=cycle_identity,
            snapshot_id=snapshot_identity,
            symbol=configuration.symbol,
            primary_timeframe=configuration.primary_timeframe,
            replay_time=replay_time,
            decision_cutoff=view.decision_cutoff,
            market_snapshot=ArtifactReference(
                artifact_id=snapshot_identity,
                schema_version=snapshot.schema_version,
                digest=snapshot_hash,
            ),
            market_features=ArtifactReference(
                artifact_id=deterministic_id("features", {"snapshot_id": snapshot_identity}),
                schema_version=features.schema_version,
                digest=features_hash,
            ),
            replay_configuration_digest=configuration_hash,
            generated_at=replay_time,
        )
        return ReplayBuildResult(frame=frame, snapshot=snapshot, features=features)


def freeze_replay_decision(
    frame: ReplayFrame,
    proposal: TradeProposal,
    *,
    source: ReplayDecisionSource,
    frozen_at: datetime,
    risk_decision: RiskDecision | None = None,
) -> FrozenReplayDecision:
    """Freeze a proposal and validate any persisted M3 decision without repair."""
    proposal_hash = content_digest(proposal)
    risk_link: PersistedRiskDecisionLink | None = None
    if risk_decision is not None:
        risk_link = PersistedRiskDecisionLink(
            proposal_digest=proposal_hash,
            risk_decision_digest=content_digest(risk_decision),
            risk_decision=risk_decision,
        )
    try:
        return FrozenReplayDecision(
            frozen_decision_id=deterministic_id(
                "decision", {"frame_id": frame.frame_id, "proposal_digest": proposal_hash}
            ),
            replay_id=frame.replay_id,
            frame_id=frame.frame_id,
            cycle_id=frame.cycle_id,
            snapshot_id=frame.snapshot_id,
            symbol=frame.symbol,
            decision_cutoff=frame.decision_cutoff,
            frozen_at=frozen_at,
            source=source,
            proposal=proposal,
            proposal_digest=proposal_hash,
            risk_link=risk_link,
        )
    except ValidationError as exc:
        category = (
            ReplayErrorCategory.INVALID_RISK_LINKAGE
            if risk_decision is not None
            else ReplayErrorCategory.INVALID_PROPOSAL
        )
        raise ReplayError(category, "historical decision linkage is incompatible") from exc
