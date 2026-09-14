"""Provider-free end-to-end M10 SHADOW qualification acceptance."""

from ai_trading_team.replay.serialization import canonical_replay_bytes
from ai_trading_team.schemas.enums import (
    GraduationDisposition,
    QualificationEvidenceLifecycle,
    QualificationEvidenceValidity,
)
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationEvidenceDataset,
    QualificationRun,
    ShadowGraduationEvaluation,
)
from tests.fakes.qualification import EVALUATED_AT, qualification_bundle


def _run() -> tuple[
    QualificationRun,
    QualificationEvidenceDataset,
    ShadowGraduationEvaluation,
    QualificationEvidenceDataset,
    CurrentQualificationStatus,
]:
    _, service, sealed, manifest, policy, run = qualification_bundle()
    evaluation, evaluated, status = service.evaluate(
        run,
        sealed,
        manifest,
        policy,
        evaluated_at=EVALUATED_AT,
    )
    return run, sealed, evaluation, evaluated, status


def test_fake_provider_qualification_is_reproducible_and_review_only() -> None:
    first = _run()
    second = _run()

    assert first == second
    evaluation = first[2]
    evaluated = first[3]
    status = first[4]
    assert evaluation.disposition is GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW
    assert evaluated.lifecycle is QualificationEvidenceLifecycle.EVALUATED
    assert status.validity_assessment.state is QualificationEvidenceValidity.VALID
    assert status.currently_eligible_for_demo_review
    assert canonical_replay_bytes(first) == canonical_replay_bytes(second)
