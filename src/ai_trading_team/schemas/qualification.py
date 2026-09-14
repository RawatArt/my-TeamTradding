"""Immutable M10 qualification, evidence, metric, and graduation contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    ContentDigest,
    CoreModel,
    FiniteDecimal,
    Identifier,
    NonNegativeDecimal,
    SchemaVersion,
    Symbol,
)
from ai_trading_team.schemas.enums import (
    GraduationDisposition,
    ModelProvider,
    QualificationCollectionMode,
    QualificationComparator,
    QualificationEvidenceLifecycle,
    QualificationEvidenceValidity,
    QualificationGateCategory,
    QualificationGateStatus,
    QualificationIncidentCategory,
    QualificationMetricStatus,
    QualificationReasonCode,
    Timeframe,
)
from ai_trading_team.schemas.evaluation import PerformanceSummary, TradeOutcome
from ai_trading_team.schemas.historical import DatasetPartition
from ai_trading_team.schemas.observation import (
    AcceptanceEvidenceReference,
    ContinuousDecisionRecord,
    DecisionCandleClaim,
    SymbolTimestampAcceptanceRecord,
)
from ai_trading_team.schemas.runtime import PricingProfile

Rate = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"), allow_inf_nan=False)]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


class QualificationArtifactReference(CoreModel):
    artifact_type: Identifier
    artifact_id: Identifier
    schema_version: SchemaVersion
    content_digest: ContentDigest


class QualifiedRoleAssignment(CoreModel):
    """One exact provider/model/role generation, never a provider-family inference."""

    role: Identifier
    provider: ModelProvider
    model_identifier: Identifier
    agent_version: SchemaVersion
    prompt_id: Identifier
    prompt_version: SchemaVersion
    prompt_digest: ContentDigest
    adapter_version: SchemaVersion
    provider_sdk_version: str = Field(min_length=1, max_length=128)
    capability_profile_digest: ContentDigest
    runtime_profile_ref: Identifier
    runtime_profile_digest: ContentDigest
    input_schema_digest: ContentDigest
    output_schema_digest: ContentDigest
    m5_live_smoke: AcceptanceEvidenceReference | None = None
    m6_full_shadow: AcceptanceEvidenceReference | None = None
    m9_feature_input: AcceptanceEvidenceReference | None = None
    m9_continuous_acceptance: QualificationArtifactReference | None = None
    acceptance_valid_until: datetime | None = None

    _normalize_expiry = field_validator("acceptance_valid_until")(_optional_utc)

    @model_validator(mode="after")
    def validate_real_provider_chain(self) -> Self:
        chain = (
            self.m5_live_smoke,
            self.m6_full_shadow,
            self.m9_feature_input,
            self.m9_continuous_acceptance,
            self.acceptance_valid_until,
        )
        if self.provider is ModelProvider.FAKE:
            if any(item is not None for item in chain):
                raise ValueError("fake assignments cannot claim real-provider acceptance")
        elif any(item is None for item in chain):
            raise ValueError("real-provider assignments require the complete M5/M6/M9 chain")
        return self


class QualificationDependencyManifest(CoreModel):
    """Complete material generation identity for one qualification run."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    generation_id: Identifier
    assignments: tuple[QualifiedRoleAssignment, ...] = Field(min_length=1)
    agent_market_view_version: SchemaVersion
    agent_market_view_schema_digest: ContentDigest
    feature_allowlist_version: SchemaVersion
    feature_allowlist_digest: ContentDigest
    feature_engine_version: SchemaVersion
    feature_engine_digest: ContentDigest
    risk_engine_version: SchemaVersion
    risk_policy_digest: ContentDigest
    orchestration_policy_version: SchemaVersion
    orchestration_policy_digest: ContentDigest
    outcome_policy_version: SchemaVersion
    outcome_policy_digest: ContentDigest
    budget_policy_ref: Identifier
    budget_policy_version: SchemaVersion
    budget_policy_digest: ContentDigest
    pricing_profile_refs: tuple[QualificationArtifactReference, ...] = ()
    symbol_timestamp_acceptance: SymbolTimestampAcceptanceRecord
    created_at: datetime

    _normalize_time = field_validator("created_at")(_utc)

    @model_validator(mode="after")
    def validate_unique_assignments(self) -> Self:
        roles = tuple(item.role for item in self.assignments)
        if len(set(roles)) != len(roles):
            raise ValueError("qualification role assignments must be unique")
        pricing_ids = tuple(item.artifact_id for item in self.pricing_profile_refs)
        if len(set(pricing_ids)) != len(pricing_ids):
            raise ValueError("pricing profile references must be unique")
        return self


class QualificationPartitionDeclaration(CoreModel):
    """Predeclared context and evaluation ranges with explicit collection purpose."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    declaration_id: Identifier
    partition: DatasetPartition
    collection_mode: QualificationCollectionMode
    declared_at: datetime
    evidence_source_ref: Identifier
    evidence_source_digest: ContentDigest

    _normalize_time = field_validator("declared_at")(_utc)

    @model_validator(mode="after")
    def validate_predeclaration(self) -> Self:
        if self.declared_at > self.partition.evaluation_start:
            raise ValueError("qualification partition must be declared before evaluation starts")
        return self


class QualificationIncident(CoreModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    incident_id: Identifier
    category: QualificationIncidentCategory
    occurred_at: datetime
    evidence: QualificationArtifactReference
    decision_key: Identifier | None = None
    cycle_id: Identifier | None = None
    invocation_id: Identifier | None = None

    _normalize_time = field_validator("occurred_at")(_utc)


class QualificationEvidenceDataset(CoreModel):
    """One immutable revision in OPEN -> SEALED -> EVALUATED lifecycle."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    dataset_id: Identifier
    qualification_run_id: Identifier
    generation_id: Identifier
    generation_digest: ContentDigest
    partition: QualificationPartitionDeclaration
    lifecycle: QualificationEvidenceLifecycle
    revision: PositiveInt
    previous_revision_digest: ContentDigest | None = None
    opened_at: datetime
    sealed_at: datetime | None = None
    evaluated_at: datetime | None = None
    sealed_content_digest: ContentDigest | None = None
    evaluation_reference: QualificationArtifactReference | None = None
    claims: tuple[DecisionCandleClaim, ...] = ()
    decisions: tuple[ContinuousDecisionRecord, ...] = ()
    outcomes: tuple[TradeOutcome, ...] = ()
    pricing_profiles: tuple[PricingProfile, ...] = ()
    incidents: tuple[QualificationIncident, ...] = ()
    safety_evidence: tuple[QualificationArtifactReference, ...] = Field(min_length=1)

    _normalize_opened = field_validator("opened_at")(_utc)
    _normalize_optional = field_validator("sealed_at", "evaluated_at")(_optional_utc)

    @model_validator(mode="after")
    def validate_lifecycle_and_evidence(self) -> Self:
        if self.lifecycle is QualificationEvidenceLifecycle.OPEN:
            if any(
                value is not None
                for value in (
                    self.sealed_at,
                    self.evaluated_at,
                    self.sealed_content_digest,
                    self.evaluation_reference,
                )
            ):
                raise ValueError("open evidence cannot carry seal or evaluation metadata")
        elif self.lifecycle is QualificationEvidenceLifecycle.SEALED:
            if (
                self.sealed_at is None
                or self.sealed_content_digest is None
                or self.evaluated_at is not None
                or self.evaluation_reference is not None
            ):
                raise ValueError("sealed evidence requires seal metadata only")
        elif (
            self.sealed_at is None
            or self.evaluated_at is None
            or self.sealed_content_digest is None
            or self.evaluation_reference is None
        ):
            raise ValueError("evaluated evidence requires seal and evaluation metadata")
        if self.sealed_at is not None and self.sealed_at < self.opened_at:
            raise ValueError("evidence seal cannot predate opening")
        if self.evaluated_at is not None and (
            self.sealed_at is None or self.evaluated_at < self.sealed_at
        ):
            raise ValueError("evidence evaluation cannot predate sealing")
        self._validate_unique_identity()
        self._validate_partition_membership()
        self._validate_outcome_linkage()
        return self

    def _validate_unique_identity(self) -> None:
        groups = (
            tuple(item.decision_key for item in self.claims),
            tuple(item.record_id for item in self.decisions),
            tuple(item.outcome_id for item in self.outcomes),
            tuple(item.profile_ref for item in self.pricing_profiles),
            tuple(item.incident_id for item in self.incidents),
            tuple(item.artifact_id for item in self.safety_evidence),
        )
        if any(len(values) != len(set(values)) for values in groups):
            raise ValueError("qualification evidence identities must be unique")

    def _validate_partition_membership(self) -> None:
        partition = self.partition.partition
        claim_keys = {item.decision_key for item in self.claims}
        for claim in self.claims:
            if not partition.evaluation_start <= claim.candle_close_at < partition.evaluation_end:
                raise ValueError("qualification claim is outside the evaluation range")
        for decision in self.decisions:
            if decision.decision_key not in claim_keys:
                raise ValueError("every decision must reference a retained claim")
        for outcome in self.outcomes:
            if (
                outcome.partition_id != partition.partition_id
                or outcome.partition_kind is not partition.kind
                or outcome.decision_cutoff < partition.evaluation_start
                or outcome.evaluation_ended_at > partition.evaluation_end
            ):
                raise ValueError("qualification outcome violates partition boundaries")

    def _validate_outcome_linkage(self) -> None:
        intents = {
            (
                record.cycle_id,
                record.actual_snapshot_id,
                record.shadow_record.shadow_trade_intent.proposal.proposal_id,
            ): record.shadow_record.shadow_trade_intent
            for record in self.decisions
            if record.shadow_record is not None
            and record.shadow_record.shadow_trade_intent is not None
        }
        for outcome in self.outcomes:
            key = (outcome.cycle_id, outcome.snapshot_id, outcome.proposal_id)
            intent = intents.get(key)
            if intent is None:
                raise ValueError("qualification outcome lacks an exact shadow-intent link")
            if outcome.proposal_digest != _model_digest(intent.proposal):
                raise ValueError("qualification outcome proposal digest does not match its intent")


class QualificationRun(CoreModel):
    """Sealed identity joining exact dependencies, partition, and evidence."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    qualification_run_id: Identifier
    dependency_manifest: QualificationDependencyManifest
    dependency_manifest_digest: ContentDigest
    partition: QualificationPartitionDeclaration
    symbol: Symbol
    timeframe: Literal[Timeframe.M15] = Timeframe.M15
    started_at: datetime
    completed_at: datetime
    evidence_dataset_id: Identifier
    evidence_dataset_digest: ContentDigest
    created_at: datetime

    _normalize_time = field_validator("started_at", "completed_at", "created_at")(_utc)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        if not self.started_at <= self.completed_at <= self.created_at:
            raise ValueError("qualification run timestamps must be ordered")
        if self.started_at < self.partition.partition.evaluation_start:
            raise ValueError("qualification run cannot start before evaluation range")
        if self.completed_at > self.partition.partition.evaluation_end:
            raise ValueError("qualification run cannot end after evaluation range")
        acceptance = self.dependency_manifest.symbol_timestamp_acceptance
        if acceptance.symbol != self.symbol:
            raise ValueError("qualification symbol must match timestamp acceptance")
        return self


class QualificationValidityAssessment(CoreModel):
    """Current evidence validity; historical graduation records remain unchanged."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    assessment_id: Identifier
    qualification_run_id: Identifier
    evidence_dataset_id: Identifier
    evidence_dataset_digest: ContentDigest
    dependency_manifest_digest: ContentDigest
    state: QualificationEvidenceValidity
    assessed_at: datetime
    valid_until: datetime | None = None
    reasons: tuple[str, ...] = ()
    evidence: tuple[QualificationArtifactReference, ...] = Field(min_length=1)

    _normalize_assessed = field_validator("assessed_at")(_utc)
    _normalize_valid_until = field_validator("valid_until")(_optional_utc)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state is QualificationEvidenceValidity.VALID:
            if self.reasons:
                raise ValueError("valid evidence cannot carry invalidity reasons")
            if self.valid_until is None or self.valid_until <= self.assessed_at:
                raise ValueError("valid evidence requires a future validity boundary")
        elif not self.reasons:
            raise ValueError("non-valid evidence requires explicit reasons")
        return self


class ShadowGraduationPolicy(CoreModel):
    """Explicit reviewed thresholds; no universal profitability defaults."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_ref: Identifier
    policy_version: SchemaVersion
    minimum_completed_decision_cycles: PositiveInt
    minimum_ai_invoked_cycles: PositiveInt
    minimum_trade_candidates: PositiveInt
    minimum_risk_approved_intents: PositiveInt
    minimum_resolved_outcomes: PositiveInt
    maximum_runtime_failure_rate: Rate
    maximum_provider_failure_rate: Rate
    maximum_abandoned_cycles: NonNegativeInt
    maximum_unexplained_abandoned_cycles: NonNegativeInt
    maximum_total_assessed_observed_cost: NonNegativeDecimal
    maximum_projected_30d_cost: NonNegativeDecimal
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    expected_decisions_per_30d: PositiveInt
    minimum_expectancy_r: FiniteDecimal | None = None
    minimum_profit_factor: NonNegativeDecimal | None = None
    maximum_sequence_max_drawdown_r: NonNegativeDecimal | None = None
    maximum_ambiguous_rate: Rate
    maximum_unresolved_rate: Rate
    minimum_win_rate: Rate | None = None
    win_rate_justification: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def prevent_win_rate_only_graduation(self) -> Self:
        substantive = (
            self.minimum_expectancy_r,
            self.minimum_profit_factor,
            self.maximum_sequence_max_drawdown_r,
        )
        if all(value is None for value in substantive):
            raise ValueError("graduation requires a non-win-rate trading-performance rule")
        if (self.minimum_win_rate is None) != (self.win_rate_justification is None):
            raise ValueError("a win-rate gate requires an explicit reviewed justification")
        return self


class QualificationMetric(CoreModel):
    status: QualificationMetricStatus
    value: FiniteDecimal | None
    unit: Identifier
    evidence: tuple[QualificationArtifactReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.status is QualificationMetricStatus.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("unavailable qualification metric cannot carry a value")
        elif self.value is None:
            raise ValueError("available qualification metric requires a value")
        return self


class QualificationGateRule(CoreModel):
    comparator: QualificationComparator
    threshold: FiniteDecimal
    unit: Identifier


class QualificationGateResult(CoreModel):
    gate_id: Identifier
    category: QualificationGateCategory
    metric_name: Identifier
    measurement: QualificationMetric
    required_rule: QualificationGateRule
    status: QualificationGateStatus
    reason_code: QualificationReasonCode | None = None
    policy_ref: Identifier
    policy_version: SchemaVersion
    policy_digest: ContentDigest

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if (self.status is QualificationGateStatus.FAIL) != (self.reason_code is not None):
            raise ValueError("only failed gates require a reason code")
        return self


class QualificationSampleSummary(CoreModel):
    claimed_decisions: NonNegativeInt
    completed_decisions: NonNegativeInt
    ai_invoked_cycles: NonNegativeInt
    trade_candidates: NonNegativeInt
    risk_approved_intents: NonNegativeInt
    resolved_outcomes: NonNegativeInt


class QualificationOperationalSummary(CoreModel):
    runtime_failure_count: NonNegativeInt
    runtime_failure_rate: QualificationMetric
    provider_runtime_failure_count: NonNegativeInt
    provider_runtime_failure_rate: QualificationMetric
    duplicate_decision_count: NonNegativeInt
    abandoned_cycle_count: NonNegativeInt
    unexplained_abandoned_cycle_count: NonNegativeInt
    trace_mismatch_count: NonNegativeInt
    schema_validation_failure_count: NonNegativeInt
    source_revision_count: NonNegativeInt
    timestamp_eligibility_current: bool


class QualificationSafetySummary(CoreModel):
    risk_engine_bypass_count: NonNegativeInt
    unapproved_shadow_intent_count: NonNegativeInt
    confidence_risk_coupling_count: NonNegativeInt
    execution_or_order_mutation_count: NonNegativeInt
    demo_invocation_count: NonNegativeInt
    live_invocation_count: NonNegativeInt
    provider_fallback_count: NonNegativeInt
    strategy_mutation_count: NonNegativeInt
    prompt_self_mutation_count: NonNegativeInt


class ObservedCostSummary(CoreModel):
    """Observed costs only; no projected value may enter this model."""

    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    settled_observed_cost: NonNegativeDecimal
    conservative_uncertain_reserved_cost: NonNegativeDecimal
    total_assessed_observed_cost: NonNegativeDecimal
    observed_decision_count: NonNegativeInt
    observed_ai_invoked_cycle_count: NonNegativeInt
    observed_evidence_duration_seconds: NonNegativeDecimal
    dispatched_attempt_count: NonNegativeInt
    cost_status: QualificationMetricStatus

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        if self.total_assessed_observed_cost != (
            self.settled_observed_cost + self.conservative_uncertain_reserved_cost
        ):
            raise ValueError("observed assessed cost must equal settled plus uncertain reserve")
        return self


class ProjectedCostSummary(CoreModel):
    """Policy projection only; never actual provider spend or billing."""

    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    projected_30d_cost: NonNegativeDecimal | None
    projection_status: QualificationMetricStatus
    projection_policy_ref: Identifier
    projection_policy_version: SchemaVersion
    expected_decisions_per_30d: PositiveInt
    projection_basis: Literal["OBSERVED_COST_PER_COMPLETED_DECISION"]
    observed_cost_summary_digest: ContentDigest

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.projection_status is QualificationMetricStatus.UNAVAILABLE:
            if self.projected_30d_cost is not None:
                raise ValueError("unavailable projection cannot carry a value")
        elif self.projected_30d_cost is None:
            raise ValueError("available projection requires a value")
        return self


class QualificationTradingSummary(CoreModel):
    outcome_count: NonNegativeInt
    resolved_count: NonNegativeInt
    ambiguous_count: NonNegativeInt
    unresolved_count: NonNegativeInt
    ambiguous_rate: QualificationMetric
    unresolved_rate: QualificationMetric
    performance: PerformanceSummary | None = None


class ShadowGraduationEvaluation(CoreModel):
    """Immutable historical gate result; current validity is assessed separately."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_id: Identifier
    qualification_run_id: Identifier
    evidence_dataset_id: Identifier
    evidence_dataset_digest: ContentDigest
    validity_assessment_reference: QualificationArtifactReference
    policy_ref: Identifier
    policy_version: SchemaVersion
    policy_digest: ContentDigest
    evaluated_at: datetime
    sample_summary: QualificationSampleSummary
    operational_summary: QualificationOperationalSummary
    safety_summary: QualificationSafetySummary
    observed_cost: ObservedCostSummary
    projected_cost: ProjectedCostSummary
    trading_summary: QualificationTradingSummary
    gate_results: tuple[QualificationGateResult, ...] = Field(min_length=1)
    disposition: GraduationDisposition
    evaluation_digest: ContentDigest

    _normalize_time = field_validator("evaluated_at")(_utc)

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        gate_ids = tuple(item.gate_id for item in self.gate_results)
        if gate_ids != tuple(sorted(gate_ids)) or len(gate_ids) != len(set(gate_ids)):
            raise ValueError("graduation gates must be uniquely and canonically ordered")
        all_pass = all(item.status is QualificationGateStatus.PASS for item in self.gate_results)
        if all_pass != (
            self.disposition is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
        ):
            raise ValueError("graduation disposition must be derived from all gate results")
        return self


class CurrentQualificationStatus(CoreModel):
    """Current eligibility = historical gate pass AND currently valid evidence."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    qualification_run_id: Identifier
    graduation_evaluation_reference: QualificationArtifactReference
    graduation_disposition: GraduationDisposition
    validity_assessment: QualificationValidityAssessment
    currently_eligible_for_demo_review: bool
    assessed_at: datetime

    _normalize_time = field_validator("assessed_at")(_utc)

    @model_validator(mode="after")
    def validate_current_status(self) -> Self:
        expected = (
            self.graduation_disposition
            is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
            and self.validity_assessment.state is QualificationEvidenceValidity.VALID
        )
        if self.currently_eligible_for_demo_review != expected:
            raise ValueError("current eligibility must combine validity and graduation result")
        return self


class QualificationPerformanceReviewInput(CoreModel):
    """Offline advisory reference; excluded from every graduation calculation."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    qualification_run_id: Identifier
    evaluation_reference: QualificationArtifactReference
    validity_reference: QualificationArtifactReference
    prepared_at: datetime
    automatic_strategy_change_permitted: Literal[False] = False
    threshold_change_permitted: Literal[False] = False
    mode_change_permitted: Literal[False] = False

    _normalize_time = field_validator("prepared_at")(_utc)


def _model_digest(model: CoreModel) -> ContentDigest:
    """Use the repository-wide canonical serialization for exact linkage."""
    from ai_trading_team.replay.serialization import content_digest

    return content_digest(model)
