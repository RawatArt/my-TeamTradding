"""Narrow M10 persistence and evidence-source protocols."""

from typing import Protocol

from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationEvidenceDataset,
    QualificationRun,
    QualificationValidityAssessment,
    ShadowGraduationEvaluation,
)


class QualificationRepository(Protocol):
    def append_evidence_revision(self, dataset: QualificationEvidenceDataset) -> None: ...

    def latest_evidence(self, dataset_id: str) -> QualificationEvidenceDataset | None: ...

    def append_run(self, run: QualificationRun) -> None: ...

    def get_run(self, run_id: str) -> QualificationRun | None: ...

    def append_validity(self, assessment: QualificationValidityAssessment) -> None: ...

    def latest_validity(self, run_id: str) -> QualificationValidityAssessment | None: ...

    def append_evaluation(self, evaluation: ShadowGraduationEvaluation) -> None: ...

    def get_evaluation(self, evaluation_id: str) -> ShadowGraduationEvaluation | None: ...

    def append_current_status(self, status: CurrentQualificationStatus) -> None: ...

    def finalize_evaluation(
        self,
        evaluated_dataset: QualificationEvidenceDataset,
        validity: QualificationValidityAssessment,
        evaluation: ShadowGraduationEvaluation,
        status: CurrentQualificationStatus,
    ) -> None: ...
