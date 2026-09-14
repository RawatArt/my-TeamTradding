"""Deterministic M10 evidence built from accepted M3-M9 contracts."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.features import MarketFeatureEngine
from ai_trading_team.observation.identifiers import decision_candle_content_digest
from ai_trading_team.orchestration import ShadowCycleOrchestrator
from ai_trading_team.qualification import QualificationService
from ai_trading_team.qualification.acceptance import artifact_reference, dependency_manifest_digest
from ai_trading_team.qualification.evidence import append_evidence
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    DecisionClaimState,
    M9DecisionDisposition,
    ModelProvider,
    OutcomeBasis,
    QualificationCollectionMode,
    QualificationEvidenceLifecycle,
    Timeframe,
    TradeAction,
    TradeOutcomeStatus,
)
from ai_trading_team.schemas.evaluation import SegmentFacts, TradeOutcome
from ai_trading_team.schemas.historical import DatasetPartition
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.observation import (
    ContinuousDecisionRecord,
    DecisionCandleClaim,
    RiskContextEvidence,
    SymbolTimestampAcceptanceRecord,
)
from ai_trading_team.schemas.qualification import (
    QualificationArtifactReference,
    QualificationDependencyManifest,
    QualificationEvidenceDataset,
    QualificationPartitionDeclaration,
    QualificationRun,
    QualifiedRoleAssignment,
    ShadowGraduationPolicy,
)
from ai_trading_team.schemas.replay import OutcomeHorizon
from ai_trading_team.schemas.runtime import PricingProfile
from ai_trading_team.storage.qualification import InMemoryQualificationRepository
from ai_trading_team.storage.shadow_audit import InMemoryShadowAuditRepository
from tests.fakes.features import feature_snapshot
from tests.fakes.market import SNAPSHOT_END, SYMBOL
from tests.fakes.risk import CYCLE_ID, SNAPSHOT_ID, account_context
from tests.fakes.shadow import ScriptedShadowInvoker

RUN_ID = "qualification-run-m10-001"
DATASET_ID = "qualification-evidence-m10-001"
GENERATION_ID = "generation-m10-001"
PARTITION_ID = "partition-m10-oos-001"
EVALUATED_AT = datetime(2026, 9, 10, 12, 20, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 10, 1, tzinfo=UTC)
_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64


def qualified_shadow_evidence(
    *,
    partition_kind: DatasetPartitionKind = DatasetPartitionKind.OUT_OF_SAMPLE,
) -> tuple[
    DecisionCandleClaim,
    ContinuousDecisionRecord,
    TradeOutcome,
    PricingProfile,
]:
    base_snapshot = feature_snapshot()
    snapshot = MarketSnapshot.model_validate(
        base_snapshot.model_copy(
            update={
                "cycle_id": CYCLE_ID,
                "snapshot_id": SNAPSHOT_ID,
                "open_positions": (),
            }
        ).model_dump()
    )
    features = MarketFeatureEngine().calculate(snapshot)
    market_view = AgentMarketView.from_snapshot(snapshot, features)
    context = account_context(snapshot)
    shadow_record = asyncio.run(
        ShadowCycleOrchestrator(
            invoker=ScriptedShadowInvoker(chief_action=TradeAction.BUY),
            risk_engine=RiskEngine(RiskConstitutionSettings()),
            repository=InMemoryShadowAuditRepository(),
            clock=lambda: SNAPSHOT_END + timedelta(seconds=30),
        ).run_shadow_cycle(snapshot, context, market_view=market_view)
    )
    assert shadow_record.shadow_trade_intent is not None
    decision_candle = snapshot.candles.m15[-1]
    candle_close = decision_candle.open_time + timedelta(minutes=15)
    candle_digest = decision_candle_content_digest(decision_candle)
    decision_key = "decision-m10-001"
    claim = DecisionCandleClaim(
        decision_key=decision_key,
        cycle_id=CYCLE_ID,
        actual_snapshot_id=SNAPSHOT_ID,
        symbol=SYMBOL,
        candle_open_at=decision_candle.open_time,
        candle_close_at=candle_close,
        candle_digest=candle_digest,
        state=DecisionClaimState.COMPLETED,
        discovered_at=candle_close,
        updated_at=SNAPSHOT_END + timedelta(seconds=30),
    )
    risk_evidence = RiskContextEvidence(
        baseline_id="baseline-m10-001",
        baseline_digest=_DIGEST_A,
        account_observation_digest=content_digest(snapshot.account),
        positions_observation_digest=content_digest(snapshot.open_positions),
        context=context,
    )
    record = ContinuousDecisionRecord(
        record_id="continuous-decision-m10-001",
        decision_key=decision_key,
        cycle_id=CYCLE_ID,
        actual_snapshot_id=SNAPSHOT_ID,
        symbol=SYMBOL,
        decision_candle_digest=candle_digest,
        disposition=M9DecisionDisposition.SHADOW_RECORDED,
        recorded_at=SNAPSHOT_END + timedelta(seconds=30),
        snapshot_digest=content_digest(snapshot),
        feature_set_digest=content_digest(features),
        agent_feature_view_digest=market_view.agent_feature_view_digest,
        agent_market_view=market_view,
        risk_context_evidence=risk_evidence,
        shadow_record=shadow_record,
    )
    pricing = PricingProfile(
        profile_ref="pricing-fake-m10-v1",
        profile_version="1.0.0",
        provider=ModelProvider.FAKE,
        model_identifier="fake-structured-model",
        currency="USD",
        input_cost_per_million_tokens=Decimal("1"),
        output_cost_per_million_tokens=Decimal("1"),
        valid_from=datetime(2026, 9, 1, tzinfo=UTC),
        valid_until=VALID_UNTIL,
    )
    return claim, record, _winning_outcome(record, candle_close, partition_kind), pricing


def _winning_outcome(
    record: ContinuousDecisionRecord,
    decision_cutoff: datetime,
    partition_kind: DatasetPartitionKind,
) -> TradeOutcome:
    assert record.shadow_record is not None
    intent = record.shadow_record.shadow_trade_intent
    assert intent is not None
    proposal = intent.proposal
    assert record.actual_snapshot_id is not None
    assert proposal.entry is not None
    assert proposal.stop_loss is not None
    assert proposal.take_profit is not None
    risk_unit = abs(proposal.entry - proposal.stop_loss)
    favorable = abs(proposal.take_profit - proposal.entry)
    adverse = Decimal("0.00005")
    end = decision_cutoff + timedelta(minutes=15)
    return TradeOutcome(
        outcome_id="outcome-m10-001",
        replay_id="forward-shadow-m10-001",
        frame_id="frame-m10-001",
        cycle_id=record.cycle_id,
        snapshot_id=record.actual_snapshot_id,
        proposal_id=proposal.proposal_id,
        proposal_digest=content_digest(proposal),
        dataset_id=DATASET_ID,
        dataset_digest=_DIGEST_B,
        partition_id=PARTITION_ID,
        partition_kind=partition_kind,
        symbol=record.symbol,
        side=proposal.side,
        timeframe=Timeframe.M15,
        decision_cutoff=decision_cutoff,
        evaluation_started_at=decision_cutoff,
        evaluation_ended_at=end,
        horizon=OutcomeHorizon(max_bars=1),
        bars_evaluated=1,
        status=TradeOutcomeStatus.TAKE_PROFIT_REACHED,
        resolution_candle_open_at=decision_cutoff,
        resolution_candle_close_at=end,
        bars_to_resolution=1,
        seconds_to_resolution=Decimal("900"),
        entry=proposal.entry,
        stop_loss=proposal.stop_loss,
        take_profit=proposal.take_profit,
        risk_unit=risk_unit,
        realized_r_multiple=favorable / risk_unit,
        maximum_favorable_excursion=favorable,
        maximum_adverse_excursion=adverse,
        mfe_r=favorable / risk_unit,
        mae_r=adverse / risk_unit,
        outcome_candle_digest="sha256:" + "c" * 64,
        evaluation_policy_digest="sha256:" + "d" * 64,
        outcome_basis=OutcomeBasis.THEORETICAL_LEVEL_TOUCH_NO_COSTS,
        segment_facts=SegmentFacts(
            direction=proposal.side,
            timeframe=Timeframe.M15,
            partition=partition_kind,
        ),
    )


def partition_declaration(
    *,
    kind: DatasetPartitionKind = DatasetPartitionKind.OUT_OF_SAMPLE,
    collection_mode: QualificationCollectionMode = QualificationCollectionMode.FORWARD_SHADOW,
) -> QualificationPartitionDeclaration:
    return QualificationPartitionDeclaration(
        declaration_id="qualification-partition-declaration-m10-001",
        partition=DatasetPartition(
            partition_id=PARTITION_ID,
            kind=kind,
            context_start=datetime(2026, 9, 1, tzinfo=UTC),
            evaluation_start=datetime(2026, 9, 10, 11, tzinfo=UTC),
            evaluation_end=datetime(2026, 9, 10, 13, tzinfo=UTC),
        ),
        collection_mode=collection_mode,
        declared_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        evidence_source_ref="m9-observation-repository",
        evidence_source_digest=_DIGEST_A,
    )


def dependency_manifest(
    record: ContinuousDecisionRecord,
    pricing: PricingProfile | None,
) -> QualificationDependencyManifest:
    assert record.shadow_record is not None
    assert record.agent_market_view is not None
    assert record.risk_context_evidence is not None
    assert record.agent_market_view.features is not None
    roles = tuple(
        QualifiedRoleAssignment(
            role=item.trace.agent_role.value,
            provider=item.trace.provider,
            model_identifier=item.trace.model_identifier,
            agent_version=item.trace.agent_version,
            prompt_id=item.trace.prompt_id,
            prompt_version=item.trace.prompt_version,
            prompt_digest=item.trace.prompt_digest,
            adapter_version="1.0.0",
            provider_sdk_version="fake-contract-1.0.0",
            capability_profile_digest=_DIGEST_A,
            runtime_profile_ref=item.trace.runtime_profile_ref,
            runtime_profile_digest=_DIGEST_B,
            input_schema_digest=_DIGEST_A,
            output_schema_digest=_DIGEST_B,
        )
        for item in record.shadow_record.decision_cycle.invocations
    )
    view = record.agent_market_view
    feature_view = view.features
    assert feature_view is not None
    timestamp_acceptance = SymbolTimestampAcceptanceRecord(
        acceptance_id="timestamp-acceptance-m10-001",
        symbol=record.symbol,
        timeframes=(Timeframe.M15, Timeframe.H1, Timeframe.H4),
        account_ref=record.risk_context_evidence.context.account_ref,
        adapter_version="1.0.0",
        validation_policy_digest=_DIGEST_A,
        test_result_id="timestamp-result-m10-001",
        tested_at=datetime(2026, 9, 1, tzinfo=UTC),
        expires_at=VALID_UNTIL,
    )
    return QualificationDependencyManifest(
        generation_id=GENERATION_ID,
        assignments=roles,
        agent_market_view_version=view.schema_version,
        agent_market_view_schema_digest=content_digest(AgentMarketView.model_json_schema()),
        feature_allowlist_version=feature_view.allowlist_version,
        feature_allowlist_digest=content_digest(feature_view.model_json_schema()),
        feature_engine_version=feature_view.source_feature_engine_version,
        feature_engine_digest=_DIGEST_A,
        risk_engine_version="1.0.0",
        risk_policy_digest=_DIGEST_B,
        orchestration_policy_version="1.0.0",
        orchestration_policy_digest=_DIGEST_A,
        outcome_policy_version="1.0.0",
        outcome_policy_digest=_DIGEST_B,
        budget_policy_ref="budget-shadow-test",
        budget_policy_version="1.0.0",
        budget_policy_digest=_DIGEST_A,
        pricing_profile_refs=(
            ()
            if pricing is None
            else (
                artifact_reference(
                    "pricing_profile",
                    pricing.profile_ref,
                    pricing,
                    schema_version=pricing.profile_version,
                ),
            )
        ),
        symbol_timestamp_acceptance=timestamp_acceptance,
        created_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
    )


def graduation_policy() -> ShadowGraduationPolicy:
    return ShadowGraduationPolicy(
        policy_ref="shadow-graduation-policy-m10",
        policy_version="1.0.0",
        minimum_completed_decision_cycles=1,
        minimum_ai_invoked_cycles=1,
        minimum_trade_candidates=1,
        minimum_risk_approved_intents=1,
        minimum_resolved_outcomes=1,
        maximum_runtime_failure_rate=Decimal("0"),
        maximum_provider_failure_rate=Decimal("0"),
        maximum_abandoned_cycles=0,
        maximum_unexplained_abandoned_cycles=0,
        maximum_total_assessed_observed_cost=Decimal("1"),
        maximum_projected_30d_cost=Decimal("1"),
        currency="USD",
        expected_decisions_per_30d=30,
        minimum_expectancy_r=Decimal("1"),
        maximum_ambiguous_rate=Decimal("0"),
        maximum_unresolved_rate=Decimal("0"),
    )


def qualification_bundle(
    *,
    partition_kind: DatasetPartitionKind = DatasetPartitionKind.OUT_OF_SAMPLE,
    collection_mode: QualificationCollectionMode = QualificationCollectionMode.FORWARD_SHADOW,
    include_pricing: bool = True,
    repository: InMemoryQualificationRepository | None = None,
) -> tuple[
    InMemoryQualificationRepository,
    QualificationService,
    QualificationEvidenceDataset,
    QualificationDependencyManifest,
    ShadowGraduationPolicy,
    QualificationRun,
]:
    claim, decision, outcome, pricing = qualified_shadow_evidence(
        partition_kind=partition_kind
    )
    active_pricing = pricing if include_pricing else None
    manifest = dependency_manifest(decision, active_pricing)
    declaration = partition_declaration(
        kind=partition_kind,
        collection_mode=collection_mode,
    )
    safety_ref = QualificationArtifactReference(
        artifact_type="safety_test_result",
        artifact_id="safety-m0-m10",
        schema_version="1.0.0",
        content_digest=_DIGEST_A,
    )
    opened = QualificationEvidenceDataset(
        dataset_id=DATASET_ID,
        qualification_run_id=RUN_ID,
        generation_id=GENERATION_ID,
        generation_digest=dependency_manifest_digest(manifest),
        partition=declaration,
        lifecycle=QualificationEvidenceLifecycle.OPEN,
        revision=1,
        opened_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        safety_evidence=(safety_ref,),
    )
    active_repository = repository or InMemoryQualificationRepository()
    active_repository.append_evidence_revision(opened)
    collected = append_evidence(
        opened,
        claims=(claim,),
        decisions=(decision,),
        outcomes=(outcome,),
        pricing_profiles=() if active_pricing is None else (active_pricing,),
    )
    active_repository.append_evidence_revision(collected)
    service = QualificationService(active_repository)
    sealed = service.seal(
        collected,
        sealed_at=datetime(2026, 9, 10, 12, 16, tzinfo=UTC),
    )
    run = service.create_run(
        qualification_run_id=RUN_ID,
        manifest=manifest,
        dataset=sealed,
        symbol=SYMBOL,
        started_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        completed_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
        created_at=datetime(2026, 9, 10, 12, 17, tzinfo=UTC),
    )
    return active_repository, service, sealed, manifest, graduation_policy(), run
