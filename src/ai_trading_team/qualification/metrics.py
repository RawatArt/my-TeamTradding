"""Deterministic M10 operational, safety, cost, sample, and trading summaries."""

from datetime import datetime
from decimal import Context, Decimal, localcontext

from ai_trading_team.evaluation.metrics import summarize_performance
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    BudgetReservationState,
    DecisionClaimState,
    M9DecisionDisposition,
    ObservationFailureCategory,
    QualificationIncidentCategory,
    QualificationMetricStatus,
    RiskDecisionStatus,
    TradeOutcomeStatus,
)
from ai_trading_team.schemas.qualification import (
    ObservedCostSummary,
    ProjectedCostSummary,
    QualificationArtifactReference,
    QualificationEvidenceDataset,
    QualificationMetric,
    QualificationOperationalSummary,
    QualificationSafetySummary,
    QualificationSampleSummary,
    QualificationTradingSummary,
    ShadowGraduationPolicy,
)
from ai_trading_team.schemas.runtime import PricingProfile

_CONTEXT = Context(prec=50)


def evidence_reference(dataset: QualificationEvidenceDataset) -> QualificationArtifactReference:
    if dataset.sealed_content_digest is None:
        raise ValueError("metric evidence must be sealed")
    return QualificationArtifactReference(
        artifact_type="qualification_evidence_dataset",
        artifact_id=dataset.dataset_id,
        schema_version=dataset.schema_version,
        content_digest=dataset.sealed_content_digest,
    )


def summarize_samples(dataset: QualificationEvidenceDataset) -> QualificationSampleSummary:
    cycles = tuple(
        item.shadow_record.decision_cycle
        for item in dataset.decisions
        if item.shadow_record is not None
    )
    return QualificationSampleSummary(
        claimed_decisions=len(dataset.claims),
        completed_decisions=sum(
            item.state is DecisionClaimState.COMPLETED for item in dataset.claims
        ),
        ai_invoked_cycles=sum(bool(item.invocations) for item in cycles),
        trade_candidates=sum(item.trade_proposal is not None for item in cycles),
        risk_approved_intents=sum(
            item.shadow_record is not None
            and item.shadow_record.shadow_trade_intent is not None
            for item in dataset.decisions
        ),
        resolved_outcomes=sum(
            item.status
            in {
                TradeOutcomeStatus.TAKE_PROFIT_REACHED,
                TradeOutcomeStatus.STOP_LOSS_REACHED,
            }
            for item in dataset.outcomes
        ),
    )


def summarize_operational(
    dataset: QualificationEvidenceDataset, *, timestamp_eligibility_current: bool
) -> QualificationOperationalSummary:
    reference = evidence_reference(dataset)
    cycles = tuple(
        item.shadow_record.decision_cycle
        for item in dataset.decisions
        if item.shadow_record is not None
    )
    runtime_failures = sum(item.state is DecisionClaimState.FAILED for item in dataset.claims)
    runtime_failures += sum(
        item.disposition is M9DecisionDisposition.FAILED for item in dataset.decisions
    )
    provider_categories = {
        AgentFailureCategory.TIMEOUT,
        AgentFailureCategory.UNAVAILABLE_AGENT,
    }
    provider_failures = sum(
        failure.category in provider_categories
        for cycle in cycles
        for failure in cycle.agent_failures
    )
    provider_failures += _incident_count(
        dataset, QualificationIncidentCategory.PROVIDER_RUNTIME_FAILURE
    )
    dispatched = sum(
        invocation.telemetry.attempt_count > 0
        for cycle in cycles
        for invocation in cycle.invocations
    )
    abandoned = sum(item.state is DecisionClaimState.ABANDONED for item in dataset.claims)
    unexplained = _incident_count(
        dataset, QualificationIncidentCategory.UNEXPLAINED_ABANDONED_CYCLE
    )
    schema_failures = _incident_count(
        dataset, QualificationIncidentCategory.SCHEMA_VALIDATION_FAILURE
    ) + sum(
        failure.category
        in {AgentFailureCategory.INVALID_OUTPUT, AgentFailureCategory.SCHEMA_MISMATCH}
        for cycle in cycles
        for failure in cycle.agent_failures
    )
    source_revisions = _incident_count(
        dataset, QualificationIncidentCategory.SOURCE_REVISION
    ) + sum(
        item.failure_category is ObservationFailureCategory.SOURCE_CANDLE_REVISED
        for item in dataset.claims
    )
    keys = tuple(item.decision_key for item in dataset.decisions)
    return QualificationOperationalSummary(
        runtime_failure_count=runtime_failures,
        runtime_failure_rate=_rate(runtime_failures, len(dataset.claims), reference),
        provider_runtime_failure_count=provider_failures,
        provider_runtime_failure_rate=_rate(provider_failures, dispatched, reference),
        duplicate_decision_count=len(keys) - len(set(keys)),
        abandoned_cycle_count=abandoned,
        unexplained_abandoned_cycle_count=unexplained,
        trace_mismatch_count=_incident_count(
            dataset, QualificationIncidentCategory.TRACE_MISMATCH
        ),
        schema_validation_failure_count=schema_failures,
        source_revision_count=source_revisions,
        timestamp_eligibility_current=timestamp_eligibility_current,
    )


def summarize_safety(dataset: QualificationEvidenceDataset) -> QualificationSafetySummary:
    categories = tuple(item.category for item in dataset.incidents)
    unapproved_intents = 0
    for record in dataset.decisions:
        if record.shadow_record is None or record.shadow_record.shadow_trade_intent is None:
            continue
        intent = record.shadow_record.shadow_trade_intent
        if (
            intent.risk_decision.status is not RiskDecisionStatus.APPROVED
            or intent.risk_decision.position_sizing is None
        ):
            unapproved_intents += 1
    count = categories.count
    return QualificationSafetySummary(
        risk_engine_bypass_count=count(QualificationIncidentCategory.RISK_ENGINE_BYPASS),
        unapproved_shadow_intent_count=unapproved_intents,
        confidence_risk_coupling_count=count(
            QualificationIncidentCategory.CONFIDENCE_RISK_COUPLING
        ),
        execution_or_order_mutation_count=count(
            QualificationIncidentCategory.EXECUTION_OR_ORDER_MUTATION
        ),
        demo_invocation_count=count(QualificationIncidentCategory.DEMO_INVOCATION),
        live_invocation_count=count(QualificationIncidentCategory.LIVE_INVOCATION),
        provider_fallback_count=count(QualificationIncidentCategory.PROVIDER_FALLBACK),
        strategy_mutation_count=count(QualificationIncidentCategory.STRATEGY_MUTATION),
        prompt_self_mutation_count=count(
            QualificationIncidentCategory.PROMPT_SELF_MUTATION
        ),
    )


def summarize_costs(
    dataset: QualificationEvidenceDataset,
    policy: ShadowGraduationPolicy,
    *,
    run_started_at: datetime,
    run_completed_at: datetime,
) -> tuple[ObservedCostSummary, ProjectedCostSummary]:
    settled = Decimal("0")
    uncertain = Decimal("0")
    status = QualificationMetricStatus.VALID
    attempts = 0
    invoked_cycles = 0
    for record in dataset.decisions:
        if record.shadow_record is None:
            continue
        invocations = record.shadow_record.decision_cycle.invocations
        if invocations:
            invoked_cycles += 1
        for invocation in invocations:
            telemetry = invocation.telemetry
            attempts += telemetry.attempt_count
            if telemetry.attempt_count and not _pricing_covers(
                dataset.pricing_profiles,
                invocation.trace.provider,
                invocation.trace.model_identifier,
                invocation.trace.request_started_at,
            ):
                status = QualificationMetricStatus.UNAVAILABLE
            for reservation in telemetry.attempt_reservations:
                if reservation.state is BudgetReservationState.SETTLED:
                    if reservation.settled_amount is None:
                        status = QualificationMetricStatus.UNAVAILABLE
                    else:
                        settled += reservation.settled_amount
                elif reservation.state is BudgetReservationState.UNCERTAIN:
                    uncertain += reservation.reserved_amount
                    if status is QualificationMetricStatus.VALID:
                        status = QualificationMetricStatus.UNCERTAIN
                elif reservation.state in {
                    BudgetReservationState.RESERVED,
                    BudgetReservationState.DISPATCHED,
                }:
                    status = QualificationMetricStatus.UNAVAILABLE
    assessed = settled + uncertain
    observed = ObservedCostSummary(
        currency=policy.currency,
        settled_observed_cost=settled,
        conservative_uncertain_reserved_cost=uncertain,
        total_assessed_observed_cost=assessed,
        observed_decision_count=len(dataset.decisions),
        observed_ai_invoked_cycle_count=invoked_cycles,
        observed_evidence_duration_seconds=Decimal(
            str((run_completed_at - run_started_at).total_seconds())
        ),
        dispatched_attempt_count=attempts,
        cost_status=status,
    )
    projected_value: Decimal | None = None
    projection_status = status
    completed = sum(item.state is DecisionClaimState.COMPLETED for item in dataset.claims)
    if completed == 0 or status is QualificationMetricStatus.UNAVAILABLE:
        projection_status = QualificationMetricStatus.UNAVAILABLE
    else:
        with localcontext(_CONTEXT):
            projected_value = assessed / Decimal(completed) * Decimal(
                policy.expected_decisions_per_30d
            )
    projected = ProjectedCostSummary(
        currency=policy.currency,
        projected_30d_cost=projected_value,
        projection_status=projection_status,
        projection_policy_ref=policy.policy_ref,
        projection_policy_version=policy.policy_version,
        expected_decisions_per_30d=policy.expected_decisions_per_30d,
        projection_basis="OBSERVED_COST_PER_COMPLETED_DECISION",
        observed_cost_summary_digest=content_digest(observed),
    )
    return observed, projected


def summarize_trading(dataset: QualificationEvidenceDataset) -> QualificationTradingSummary:
    reference = evidence_reference(dataset)
    outcomes = dataset.outcomes
    resolved = sum(
        item.status
        in {
            TradeOutcomeStatus.TAKE_PROFIT_REACHED,
            TradeOutcomeStatus.STOP_LOSS_REACHED,
        }
        for item in outcomes
    )
    ambiguous = sum(
        item.status is TradeOutcomeStatus.AMBIGUOUS_INTRABAR for item in outcomes
    )
    unresolved = sum(
        item.status is TradeOutcomeStatus.UNRESOLVED_HORIZON for item in outcomes
    )
    performance = summarize_performance(outcomes) if outcomes else None
    return QualificationTradingSummary(
        outcome_count=len(outcomes),
        resolved_count=resolved,
        ambiguous_count=ambiguous,
        unresolved_count=unresolved,
        ambiguous_rate=_rate(ambiguous, len(outcomes), reference),
        unresolved_rate=_rate(unresolved, len(outcomes), reference),
        performance=performance,
    )


def _rate(
    numerator: int,
    denominator: int,
    evidence: QualificationArtifactReference,
) -> QualificationMetric:
    if denominator == 0:
        return QualificationMetric(
            status=QualificationMetricStatus.UNAVAILABLE,
            value=None,
            unit="RATIO",
            evidence=(evidence,),
        )
    with localcontext(_CONTEXT):
        value = Decimal(numerator) / Decimal(denominator)
    return QualificationMetric(
        status=QualificationMetricStatus.VALID,
        value=value,
        unit="RATIO",
        evidence=(evidence,),
    )


def _incident_count(
    dataset: QualificationEvidenceDataset, category: QualificationIncidentCategory
) -> int:
    return sum(item.category is category for item in dataset.incidents)


def _pricing_covers(
    profiles: tuple[PricingProfile, ...],
    provider: object,
    model_identifier: str,
    at: datetime,
) -> bool:
    matches = tuple(
        item
        for item in profiles
        if item.provider is provider
        and item.model_identifier == model_identifier
        and item.valid_from <= at
        and (item.valid_until is None or at < item.valid_until)
    )
    return len(matches) == 1
