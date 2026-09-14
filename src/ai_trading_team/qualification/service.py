"""M10 qualification sealing, evaluation, and current-validity coordination."""

from datetime import datetime

from ai_trading_team.qualification.acceptance import (
    assess_validity,
    dependency_manifest_digest,
)
from ai_trading_team.qualification.errors import QualificationError
from ai_trading_team.qualification.evaluator import (
    ShadowGraduationEvaluator,
    current_qualification_status,
)
from ai_trading_team.qualification.evidence import (
    mark_evaluated,
    seal_evidence,
    verify_sealed_evidence,
)
from ai_trading_team.qualification.protocols import QualificationRepository
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    QualificationErrorCategory,
    QualificationEvidenceLifecycle,
)
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationArtifactReference,
    QualificationDependencyManifest,
    QualificationEvidenceDataset,
    QualificationRun,
    QualificationValidityAssessment,
    ShadowGraduationEvaluation,
    ShadowGraduationPolicy,
)


class QualificationService:
    """Coordinates only bounded evidence artifacts; never starts M9 or changes app mode."""

    def __init__(
        self,
        repository: QualificationRepository,
        evaluator: ShadowGraduationEvaluator | None = None,
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator or ShadowGraduationEvaluator()

    def seal(
        self, dataset: QualificationEvidenceDataset, *, sealed_at: datetime
    ) -> QualificationEvidenceDataset:
        sealed = seal_evidence(dataset, sealed_at=sealed_at)
        self._repository.append_evidence_revision(sealed)
        return sealed

    def create_run(
        self,
        *,
        qualification_run_id: str,
        manifest: QualificationDependencyManifest,
        dataset: QualificationEvidenceDataset,
        symbol: str,
        started_at: datetime,
        completed_at: datetime,
        created_at: datetime,
    ) -> QualificationRun:
        verify_sealed_evidence(dataset)
        if dataset.lifecycle is not QualificationEvidenceLifecycle.SEALED:
            raise QualificationError(
                QualificationErrorCategory.EVIDENCE_NOT_SEALED,
                "qualification run requires sealed, unevaluated evidence",
            )
        manifest_digest = dependency_manifest_digest(manifest)
        if (
            dataset.qualification_run_id != qualification_run_id
            or dataset.generation_id != manifest.generation_id
            or dataset.generation_digest != manifest_digest
        ):
            raise QualificationError(
                QualificationErrorCategory.DEPENDENCY_INCOMPATIBLE,
                "evidence and dependency generation do not match",
            )
        assert dataset.sealed_content_digest is not None
        run = QualificationRun(
            qualification_run_id=qualification_run_id,
            dependency_manifest=manifest,
            dependency_manifest_digest=manifest_digest,
            partition=dataset.partition,
            symbol=symbol,
            started_at=started_at,
            completed_at=completed_at,
            evidence_dataset_id=dataset.dataset_id,
            evidence_dataset_digest=dataset.sealed_content_digest,
            created_at=created_at,
        )
        self._repository.append_run(run)
        return run

    def evaluate(
        self,
        run: QualificationRun,
        dataset: QualificationEvidenceDataset,
        current_manifest: QualificationDependencyManifest,
        policy: ShadowGraduationPolicy,
        *,
        evaluated_at: datetime,
    ) -> tuple[
        ShadowGraduationEvaluation,
        QualificationEvidenceDataset,
        CurrentQualificationStatus,
    ]:
        validity = assess_validity(
            run,
            dataset,
            current_manifest,
            assessed_at=evaluated_at,
        )
        evaluation = self._evaluator.evaluate(
            run,
            dataset,
            validity,
            policy,
            evaluated_at=evaluated_at,
        )
        evaluation_reference = QualificationArtifactReference(
            artifact_type="shadow_graduation_evaluation",
            artifact_id=evaluation.evaluation_id,
            schema_version=evaluation.schema_version,
            content_digest=evaluation.evaluation_digest,
        )
        evaluated_dataset = mark_evaluated(
            dataset,
            evaluation_reference,
            evaluated_at=evaluated_at,
        )
        status = current_qualification_status(
            evaluation,
            validity,
            assessed_at=evaluated_at,
        )
        self._repository.finalize_evaluation(
            evaluated_dataset,
            validity,
            evaluation,
            status,
        )
        return evaluation, evaluated_dataset, status

    def reassess_current(
        self,
        run: QualificationRun,
        dataset: QualificationEvidenceDataset,
        evaluation: ShadowGraduationEvaluation,
        current_manifest: QualificationDependencyManifest,
        *,
        assessed_at: datetime,
        invalidation_reasons: tuple[str, ...] = (),
        contaminated: bool = False,
    ) -> tuple[QualificationValidityAssessment, CurrentQualificationStatus]:
        validity = assess_validity(
            run,
            dataset,
            current_manifest,
            assessed_at=assessed_at,
            invalidation_reasons=invalidation_reasons,
            contaminated=contaminated,
        )
        status = current_qualification_status(
            evaluation,
            validity,
            assessed_at=assessed_at,
        )
        self._repository.append_validity(validity)
        self._repository.append_current_status(status)
        return validity, status


def qualification_run_digest(run: QualificationRun) -> str:
    return content_digest(run)

