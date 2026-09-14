"""Deterministic M10 graduation gates; never a mode or execution controller."""

from datetime import datetime
from decimal import Decimal

from ai_trading_team.qualification.errors import QualificationError
from ai_trading_team.qualification.evidence import verify_sealed_evidence
from ai_trading_team.qualification.metrics import (
    evidence_reference,
    summarize_costs,
    summarize_operational,
    summarize_safety,
    summarize_samples,
    summarize_trading,
)
from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    GraduationDisposition,
    QualificationComparator,
    QualificationErrorCategory,
    QualificationEvidenceLifecycle,
    QualificationEvidenceValidity,
    QualificationGateCategory,
    QualificationGateStatus,
    QualificationMetricStatus,
    QualificationReasonCode,
    ResearchMetricStatus,
)
from ai_trading_team.schemas.evaluation import ResearchMetric
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationArtifactReference,
    QualificationEvidenceDataset,
    QualificationGateResult,
    QualificationGateRule,
    QualificationMetric,
    QualificationRun,
    QualificationValidityAssessment,
    ShadowGraduationEvaluation,
    ShadowGraduationPolicy,
)


class ShadowGraduationEvaluator:
    """Evaluate one sealed dataset; it cannot activate DEMO or LIVE."""

    def evaluate(
        self,
        run: QualificationRun,
        dataset: QualificationEvidenceDataset,
        validity: QualificationValidityAssessment,
        policy: ShadowGraduationPolicy,
        *,
        evaluated_at: datetime,
    ) -> ShadowGraduationEvaluation:
        verify_sealed_evidence(dataset)
        if dataset.lifecycle is not QualificationEvidenceLifecycle.SEALED:
            raise QualificationError(
                QualificationErrorCategory.EVIDENCE_NOT_SEALED,
                "graduation accepts one sealed, unevaluated evidence revision",
            )
        if validity.state is not QualificationEvidenceValidity.VALID:
            raise QualificationError(
                QualificationErrorCategory.ACCEPTANCE_INELIGIBLE,
                "initial graduation evaluation requires currently valid evidence",
            )
        if (
            run.qualification_run_id != dataset.qualification_run_id
            or run.evidence_dataset_id != dataset.dataset_id
            or run.evidence_dataset_digest != dataset.sealed_content_digest
            or validity.qualification_run_id != run.qualification_run_id
            or validity.evidence_dataset_digest != dataset.sealed_content_digest
        ):
            raise QualificationError(
                QualificationErrorCategory.INVALID_EVIDENCE,
                "run, validity, and sealed evidence identities do not match",
            )
        policy_digest = content_digest(policy)
        reference = evidence_reference(dataset)
        samples = summarize_samples(dataset)
        # Acceptance validity is evaluated separately from collection timing. Reaching
        # this point means the exact timestamp-semantics artifact is currently valid.
        operational = summarize_operational(
            dataset,
            timestamp_eligibility_current=True,
        )
        safety = summarize_safety(dataset)
        observed_cost, projected_cost = summarize_costs(
            dataset,
            policy,
            run_started_at=run.started_at,
            run_completed_at=run.completed_at,
        )
        trading = summarize_trading(dataset)
        gates: list[QualificationGateResult] = []

        def add(
            gate_id: str,
            category: QualificationGateCategory,
            metric_name: str,
            measurement: QualificationMetric,
            comparator: QualificationComparator,
            threshold: Decimal,
            reason: QualificationReasonCode,
        ) -> None:
            passed = _passes(measurement, comparator, threshold)
            gates.append(
                QualificationGateResult(
                    gate_id=gate_id,
                    category=category,
                    metric_name=metric_name,
                    measurement=measurement,
                    required_rule=QualificationGateRule(
                        comparator=comparator,
                        threshold=threshold,
                        unit=measurement.unit,
                    ),
                    status=(
                        QualificationGateStatus.PASS
                        if passed
                        else QualificationGateStatus.FAIL
                    ),
                    reason_code=None if passed else reason,
                    policy_ref=policy.policy_ref,
                    policy_version=policy.policy_version,
                    policy_digest=policy_digest,
                )
            )

        sample_rules = (
            (
                "01-sample-completed-decisions",
                "completed_decisions",
                samples.completed_decisions,
                policy.minimum_completed_decision_cycles,
            ),
            (
                "02-sample-ai-invoked-cycles",
                "ai_invoked_cycles",
                samples.ai_invoked_cycles,
                policy.minimum_ai_invoked_cycles,
            ),
            (
                "03-sample-trade-candidates",
                "trade_candidates",
                samples.trade_candidates,
                policy.minimum_trade_candidates,
            ),
            (
                "04-sample-approved-intents",
                "risk_approved_intents",
                samples.risk_approved_intents,
                policy.minimum_risk_approved_intents,
            ),
            (
                "05-sample-resolved-outcomes",
                "resolved_outcomes",
                samples.resolved_outcomes,
                policy.minimum_resolved_outcomes,
            ),
        )
        for gate_id, name, measured, threshold in sample_rules:
            add(
                gate_id,
                QualificationGateCategory.SAMPLE,
                name,
                _numeric_metric(measured, "COUNT", reference),
                QualificationComparator.GREATER_THAN_OR_EQUAL,
                Decimal(threshold),
                QualificationReasonCode.INSUFFICIENT_EVIDENCE,
            )

        add(
            "10-operational-runtime-failure-rate",
            QualificationGateCategory.OPERATIONAL,
            "runtime_failure_rate",
            operational.runtime_failure_rate,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_runtime_failure_rate,
            QualificationReasonCode.OPERATIONAL_THRESHOLD_FAILED,
        )
        add(
            "11-operational-provider-failure-rate",
            QualificationGateCategory.OPERATIONAL,
            "provider_runtime_failure_rate",
            operational.provider_runtime_failure_rate,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_provider_failure_rate,
            QualificationReasonCode.OPERATIONAL_THRESHOLD_FAILED,
        )
        operational_counts = (
            (
                "12-operational-duplicate-decisions",
                "duplicate_decision_count",
                operational.duplicate_decision_count,
                0,
            ),
            (
                "13-operational-abandoned",
                "abandoned_cycle_count",
                operational.abandoned_cycle_count,
                policy.maximum_abandoned_cycles,
            ),
            (
                "14-operational-unexplained-abandoned",
                "unexplained_abandoned_cycle_count",
                operational.unexplained_abandoned_cycle_count,
                policy.maximum_unexplained_abandoned_cycles,
            ),
            (
                "15-operational-trace-mismatch",
                "trace_mismatch_count",
                operational.trace_mismatch_count,
                0,
            ),
            (
                "16-operational-schema-failure",
                "schema_validation_failure_count",
                operational.schema_validation_failure_count,
                0,
            ),
            (
                "17-operational-source-revision",
                "source_revision_count",
                operational.source_revision_count,
                0,
            ),
        )
        for gate_id, name, measured, threshold in operational_counts:
            add(
                gate_id,
                QualificationGateCategory.OPERATIONAL,
                name,
                _numeric_metric(measured, "COUNT", reference),
                QualificationComparator.LESS_THAN_OR_EQUAL,
                Decimal(threshold),
                QualificationReasonCode.OPERATIONAL_THRESHOLD_FAILED,
            )
        add(
            "18-operational-timestamp-eligible",
            QualificationGateCategory.OPERATIONAL,
            "timestamp_eligibility_current",
            _numeric_metric(
                int(operational.timestamp_eligibility_current), "BOOLEAN", reference
            ),
            QualificationComparator.EQUAL,
            Decimal("1"),
            QualificationReasonCode.OPERATIONAL_THRESHOLD_FAILED,
        )

        safety_values = safety.model_dump(mode="python")
        for index, name in enumerate(sorted(safety_values), start=20):
            add(
                f"{index:02d}-safety-{name.replace('_', '-')}",
                QualificationGateCategory.SAFETY,
                name,
                _numeric_metric(int(safety_values[name]), "COUNT", reference),
                QualificationComparator.EQUAL,
                Decimal("0"),
                QualificationReasonCode.SAFETY_BOUNDARY_VIOLATION,
            )

        observed_metric = _numeric_metric(
            observed_cost.total_assessed_observed_cost,
            policy.currency,
            reference,
            status=observed_cost.cost_status,
        )
        add(
            "40-cost-observed-assessed",
            QualificationGateCategory.COST,
            "total_assessed_observed_cost",
            observed_metric,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_total_assessed_observed_cost,
            QualificationReasonCode.COST_THRESHOLD_FAILED,
        )
        projected_metric = (
            QualificationMetric(
                status=QualificationMetricStatus.UNAVAILABLE,
                value=None,
                unit=policy.currency,
                evidence=(reference,),
            )
            if projected_cost.projected_30d_cost is None
            else _numeric_metric(
                projected_cost.projected_30d_cost,
                policy.currency,
                reference,
                status=projected_cost.projection_status,
            )
        )
        add(
            "41-cost-projected-30d",
            QualificationGateCategory.COST,
            "projected_30d_cost",
            projected_metric,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_projected_30d_cost,
            QualificationReasonCode.COST_THRESHOLD_FAILED,
        )

        add(
            "50-partition-out-of-sample",
            QualificationGateCategory.PARTITION,
            "out_of_sample_partition",
            _numeric_metric(
                int(run.partition.partition.kind is DatasetPartitionKind.OUT_OF_SAMPLE),
                "BOOLEAN",
                reference,
            ),
            QualificationComparator.EQUAL,
            Decimal("1"),
            QualificationReasonCode.PARTITION_INELIGIBLE,
        )
        add(
            "51-trading-ambiguous-rate",
            QualificationGateCategory.TRADING,
            "ambiguous_rate",
            trading.ambiguous_rate,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_ambiguous_rate,
            QualificationReasonCode.TRADING_THRESHOLD_FAILED,
        )
        add(
            "52-trading-unresolved-rate",
            QualificationGateCategory.TRADING,
            "unresolved_rate",
            trading.unresolved_rate,
            QualificationComparator.LESS_THAN_OR_EQUAL,
            policy.maximum_unresolved_rate,
            QualificationReasonCode.TRADING_THRESHOLD_FAILED,
        )
        performance = trading.performance
        if policy.minimum_expectancy_r is not None:
            add(
                "53-trading-expectancy-r",
                QualificationGateCategory.TRADING,
                "expectancy_r",
                _research_metric(
                    None if performance is None else performance.expectancy_r,
                    "R_MULTIPLE",
                    reference,
                ),
                QualificationComparator.GREATER_THAN_OR_EQUAL,
                policy.minimum_expectancy_r,
                QualificationReasonCode.TRADING_THRESHOLD_FAILED,
            )
        if policy.minimum_profit_factor is not None:
            add(
                "54-trading-profit-factor",
                QualificationGateCategory.TRADING,
                "profit_factor",
                _research_metric(
                    None if performance is None else performance.profit_factor,
                    "RATIO",
                    reference,
                ),
                QualificationComparator.GREATER_THAN_OR_EQUAL,
                policy.minimum_profit_factor,
                QualificationReasonCode.TRADING_THRESHOLD_FAILED,
            )
        if policy.maximum_sequence_max_drawdown_r is not None:
            add(
                "55-trading-sequence-max-drawdown-r",
                QualificationGateCategory.TRADING,
                "sequence_max_drawdown_r",
                _research_metric(
                    None if performance is None else performance.sequence_max_drawdown_r,
                    "R_MULTIPLE",
                    reference,
                ),
                QualificationComparator.LESS_THAN_OR_EQUAL,
                policy.maximum_sequence_max_drawdown_r,
                QualificationReasonCode.TRADING_THRESHOLD_FAILED,
            )
        if policy.minimum_win_rate is not None:
            add(
                "56-trading-win-rate-reviewed",
                QualificationGateCategory.TRADING,
                "win_rate",
                _research_metric(
                    None if performance is None else performance.win_rate,
                    "RATIO",
                    reference,
                ),
                QualificationComparator.GREATER_THAN_OR_EQUAL,
                policy.minimum_win_rate,
                QualificationReasonCode.TRADING_THRESHOLD_FAILED,
            )

        ordered = tuple(sorted(gates, key=lambda item: item.gate_id))
        disposition = (
            GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
            if all(item.status is QualificationGateStatus.PASS for item in ordered)
            else GraduationDisposition.NOT_ELIGIBLE
        )
        validity_ref = QualificationArtifactReference(
            artifact_type="qualification_validity_assessment",
            artifact_id=validity.assessment_id,
            schema_version=validity.schema_version,
            content_digest=content_digest(validity),
        )
        identity = {
            "run_id": run.qualification_run_id,
            "dataset_digest": dataset.sealed_content_digest,
            "policy_digest": policy_digest,
            "evaluated_at": evaluated_at,
        }
        preliminary = ShadowGraduationEvaluation(
            evaluation_id=deterministic_id("shadow-graduation", identity),
            qualification_run_id=run.qualification_run_id,
            evidence_dataset_id=dataset.dataset_id,
            evidence_dataset_digest=dataset.sealed_content_digest,
            validity_assessment_reference=validity_ref,
            policy_ref=policy.policy_ref,
            policy_version=policy.policy_version,
            policy_digest=policy_digest,
            evaluated_at=evaluated_at,
            sample_summary=samples,
            operational_summary=operational,
            safety_summary=safety,
            observed_cost=observed_cost,
            projected_cost=projected_cost,
            trading_summary=trading,
            gate_results=ordered,
            disposition=disposition,
            evaluation_digest="sha256:" + "0" * 64,
        )
        digest = content_digest(
            preliminary.model_dump(mode="python", exclude={"evaluation_digest"})
        )
        return ShadowGraduationEvaluation.model_validate(
            preliminary.model_copy(update={"evaluation_digest": digest}).model_dump()
        )


def current_qualification_status(
    evaluation: ShadowGraduationEvaluation,
    validity: QualificationValidityAssessment,
    *,
    assessed_at: datetime,
) -> CurrentQualificationStatus:
    if evaluation.qualification_run_id != validity.qualification_run_id:
        raise QualificationError(
            QualificationErrorCategory.INVALID_EVIDENCE,
            "graduation evaluation and validity assessment do not match",
        )
    reference = QualificationArtifactReference(
        artifact_type="shadow_graduation_evaluation",
        artifact_id=evaluation.evaluation_id,
        schema_version=evaluation.schema_version,
        content_digest=evaluation.evaluation_digest,
    )
    current = (
        evaluation.disposition is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
        and validity.state is QualificationEvidenceValidity.VALID
    )
    return CurrentQualificationStatus(
        qualification_run_id=evaluation.qualification_run_id,
        graduation_evaluation_reference=reference,
        graduation_disposition=evaluation.disposition,
        validity_assessment=validity,
        currently_eligible_for_demo_review=current,
        assessed_at=assessed_at,
    )


def _numeric_metric(
    value: int | Decimal,
    unit: str,
    evidence: QualificationArtifactReference,
    *,
    status: QualificationMetricStatus = QualificationMetricStatus.VALID,
) -> QualificationMetric:
    if status is QualificationMetricStatus.UNAVAILABLE:
        return QualificationMetric(
            status=status,
            value=None,
            unit=unit,
            evidence=(evidence,),
        )
    return QualificationMetric(
        status=status,
        value=Decimal(value),
        unit=unit,
        evidence=(evidence,),
    )


def _research_metric(
    metric: ResearchMetric | None,
    unit: str,
    evidence: QualificationArtifactReference,
) -> QualificationMetric:
    if (
        metric is None
        or metric.status is not ResearchMetricStatus.VALID
        or metric.value is None
    ):
        return QualificationMetric(
            status=QualificationMetricStatus.UNAVAILABLE,
            value=None,
            unit=unit,
            evidence=(evidence,),
        )
    return _numeric_metric(metric.value, unit, evidence)


def _passes(
    measurement: QualificationMetric,
    comparator: QualificationComparator,
    threshold: Decimal,
) -> bool:
    if measurement.status is QualificationMetricStatus.UNAVAILABLE:
        return False
    assert measurement.value is not None
    if comparator is QualificationComparator.EQUAL:
        return measurement.value == threshold
    if comparator is QualificationComparator.LESS_THAN_OR_EQUAL:
        return measurement.value <= threshold
    return measurement.value >= threshold
