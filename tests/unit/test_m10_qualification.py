"""M10 qualification lifecycle, validity, cost, and gate tests."""

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.qualification import (
    EVALUATED_AT,
    VALID_UNTIL,
    dependency_manifest,
    graduation_policy,
    qualification_bundle,
    qualified_shadow_evidence,
)

from ai_trading_team.qualification.evidence import append_evidence, mark_evaluated
from ai_trading_team.replay.serialization import canonical_replay_bytes, content_digest
from ai_trading_team.schemas.enums import (
    DatasetPartitionKind,
    GraduationDisposition,
    ModelProvider,
    QualificationEvidenceLifecycle,
    QualificationEvidenceValidity,
    QualificationGateStatus,
    QualificationMetricStatus,
)
from ai_trading_team.schemas.qualification import QualifiedRoleAssignment, ShadowGraduationPolicy


def test_open_sealed_evaluated_lifecycle_is_immutable() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()

    with pytest.raises(Exception, match="cannot be changed or backfilled"):
        append_evidence(sealed)

    evaluation, evaluated, status = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    assert evaluated.lifecycle is QualificationEvidenceLifecycle.EVALUATED
    assert evaluated.sealed_content_digest == sealed.sealed_content_digest
    assert status.currently_eligible_for_demo_review
    assert evaluation.disposition is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
    with pytest.raises(Exception, match="cannot be changed or backfilled"):
        append_evidence(evaluated)
    assert evaluated.evaluation_reference is not None
    with pytest.raises(Exception, match="only sealed, unevaluated"):
        mark_evaluated(
            evaluated,
            evaluated.evaluation_reference,
            evaluated_at=EVALUATED_AT + timedelta(seconds=1),
        )


def test_validity_expiration_does_not_rewrite_historical_graduation() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()
    evaluation, evaluated, original = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    validity, current = service.reassess_current(
        run,
        evaluated,
        evaluation,
        manifest,
        assessed_at=VALID_UNTIL,
    )

    assert original.currently_eligible_for_demo_review
    assert evaluation.disposition is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
    assert validity.state is QualificationEvidenceValidity.EXPIRED
    assert validity.valid_until == VALID_UNTIL
    assert not current.currently_eligible_for_demo_review


def test_dependency_change_invalidates_current_eligibility() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()
    evaluation, evaluated, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )
    changed = manifest.model_copy(
        update={"risk_policy_digest": "sha256:" + "e" * 64}
    )

    validity, current = service.reassess_current(
        run,
        evaluated,
        evaluation,
        changed,
        assessed_at=EVALUATED_AT + timedelta(seconds=1),
    )

    assert validity.state is QualificationEvidenceValidity.INVALIDATED
    assert not current.currently_eligible_for_demo_review


def test_exact_role_assignment_change_invalidates_current_eligibility() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()
    evaluation, evaluated, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )
    first = manifest.assignments[0].model_copy(
        update={"prompt_digest": "sha256:" + "9" * 64}
    )
    changed = manifest.model_copy(update={"assignments": (first, *manifest.assignments[1:])})

    validity, status = service.reassess_current(
        run,
        evaluated,
        evaluation,
        changed,
        assessed_at=EVALUATED_AT + timedelta(seconds=1),
    )

    assert validity.state is QualificationEvidenceValidity.INVALIDATED
    assert not status.currently_eligible_for_demo_review


def test_real_provider_assignment_requires_complete_m5_m6_m9_acceptance_chain() -> None:
    _, decision, _, pricing = qualified_shadow_evidence()
    assignment = dependency_manifest(decision, pricing).assignments[0]
    values = assignment.model_dump(mode="python")
    values["provider"] = ModelProvider.OPENAI

    with pytest.raises(ValidationError, match="complete M5/M6/M9 chain"):
        QualifiedRoleAssignment.model_validate(values)


def test_performance_failure_is_distinct_from_evidence_invalidity() -> None:
    repository, service, sealed, manifest, policy, run = qualification_bundle()
    strict_policy = ShadowGraduationPolicy.model_validate(
        policy.model_copy(update={"minimum_expectancy_r": Decimal("2")}).model_dump()
    )

    evaluation, _, status = service.evaluate(
        run, sealed, manifest, strict_policy, evaluated_at=EVALUATED_AT
    )

    validity = repository.latest_validity(run.qualification_run_id)
    assert validity is not None
    assert validity.state is QualificationEvidenceValidity.VALID
    assert evaluation.disposition is GraduationDisposition.NOT_ELIGIBLE
    assert not status.currently_eligible_for_demo_review


def test_contaminated_evidence_is_not_currently_eligible() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()
    evaluation, evaluated, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    validity, current = service.reassess_current(
        run,
        evaluated,
        evaluation,
        manifest,
        assessed_at=EVALUATED_AT + timedelta(seconds=1),
        contaminated=True,
    )

    assert validity.state is QualificationEvidenceValidity.CONTAMINATED
    assert not current.currently_eligible_for_demo_review


def test_observed_cost_and_projected_cost_are_distinct_contracts() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle()

    evaluation, _, _ = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    observed = evaluation.observed_cost
    projected = evaluation.projected_cost
    assert observed.settled_observed_cost == Decimal("0.006")
    assert observed.conservative_uncertain_reserved_cost == Decimal("0")
    assert observed.total_assessed_observed_cost == Decimal("0.006")
    assert observed.observed_decision_count == 1
    assert observed.observed_evidence_duration_seconds == Decimal("4500")
    assert projected.projected_30d_cost == Decimal("0.180")
    assert projected.expected_decisions_per_30d == 30
    assert "projected_30d_cost" not in type(observed).model_fields
    assert "settled_observed_cost" not in type(projected).model_fields
    assert projected.observed_cost_summary_digest == content_digest(observed)


def test_missing_pricing_evidence_fails_cost_gates_closed() -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle(
        include_pricing=False
    )

    evaluation, _, status = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    assert evaluation.observed_cost.cost_status is QualificationMetricStatus.UNAVAILABLE
    assert evaluation.projected_cost.projection_status is QualificationMetricStatus.UNAVAILABLE
    assert not status.currently_eligible_for_demo_review
    assert any(
        item.gate_id.startswith("4") and item.status is QualificationGateStatus.FAIL
        for item in evaluation.gate_results
    )


def test_win_rate_cannot_be_the_only_performance_gate() -> None:
    values = graduation_policy().model_dump(mode="python")
    values.update(
        minimum_expectancy_r=None,
        minimum_profit_factor=None,
        maximum_sequence_max_drawdown_r=None,
        minimum_win_rate=Decimal("0.5"),
        win_rate_justification="Reviewed but not sufficient alone",
    )

    with pytest.raises(ValidationError, match="non-win-rate"):
        ShadowGraduationPolicy.model_validate(values)


@pytest.mark.parametrize(
    "partition_kind",
    [DatasetPartitionKind.RESEARCH, DatasetPartitionKind.VALIDATION],
)
def test_research_and_validation_partitions_cannot_qualify(
    partition_kind: DatasetPartitionKind,
) -> None:
    _, service, sealed, manifest, policy, run = qualification_bundle(
        partition_kind=partition_kind
    )

    evaluation, _, status = service.evaluate(
        run, sealed, manifest, policy, evaluated_at=EVALUATED_AT
    )

    assert evaluation.disposition is GraduationDisposition.NOT_ELIGIBLE
    assert not status.currently_eligible_for_demo_review
    partition_gate = next(
        item for item in evaluation.gate_results if item.gate_id == "50-partition-out-of-sample"
    )
    assert partition_gate.status is QualificationGateStatus.FAIL


def test_fake_provider_qualification_is_byte_deterministic() -> None:
    first = qualification_bundle()
    second = qualification_bundle()
    first_evaluation, first_dataset, first_status = first[1].evaluate(
        first[5], first[2], first[3], first[4], evaluated_at=EVALUATED_AT
    )
    second_evaluation, second_dataset, second_status = second[1].evaluate(
        second[5], second[2], second[3], second[4], evaluated_at=EVALUATED_AT
    )

    assert first_evaluation == second_evaluation
    assert first_dataset == second_dataset
    assert first_status == second_status
    assert first_evaluation.evaluation_digest == second_evaluation.evaluation_digest
    assert tuple(item.gate_id for item in first_evaluation.gate_results) == tuple(
        item.gate_id for item in second_evaluation.gate_results
    )
    assert canonical_replay_bytes(first_evaluation) == canonical_replay_bytes(
        second_evaluation
    )
