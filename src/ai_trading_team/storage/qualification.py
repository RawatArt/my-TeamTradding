"""Append-only in-memory and SQLite storage for M10 qualification artifacts."""

import sqlite3
from collections import defaultdict
from pathlib import Path
from threading import RLock

from ai_trading_team.qualification.evidence import evidence_content_digest
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import QualificationEvidenceLifecycle
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationEvidenceDataset,
    QualificationRun,
    QualificationValidityAssessment,
    ShadowGraduationEvaluation,
)


class InMemoryQualificationRepository:
    def __init__(self) -> None:
        self._evidence: dict[str, list[QualificationEvidenceDataset]] = defaultdict(list)
        self._runs: dict[str, QualificationRun] = {}
        self._validity: dict[str, list[QualificationValidityAssessment]] = defaultdict(list)
        self._evaluations: dict[str, ShadowGraduationEvaluation] = {}
        self._evaluation_by_run: dict[str, str] = {}
        self._statuses: dict[str, list[CurrentQualificationStatus]] = defaultdict(list)
        self._lock = RLock()

    def append_evidence_revision(self, dataset: QualificationEvidenceDataset) -> None:
        with self._lock:
            revisions = self._evidence[dataset.dataset_id]
            if not revisions:
                if (
                    dataset.revision != 1
                    or dataset.previous_revision_digest is not None
                    or dataset.lifecycle is not QualificationEvidenceLifecycle.OPEN
                ):
                    raise ValueError("first evidence revision must be OPEN revision one")
            else:
                previous = revisions[-1]
                if dataset.revision != previous.revision + 1:
                    raise ValueError("evidence revisions must be consecutive")
                if dataset.previous_revision_digest != content_digest(previous):
                    raise ValueError("evidence revision chain digest mismatch")
                if previous.lifecycle is QualificationEvidenceLifecycle.OPEN:
                    if dataset.lifecycle not in {
                        QualificationEvidenceLifecycle.OPEN,
                        QualificationEvidenceLifecycle.SEALED,
                    }:
                        raise ValueError("OPEN evidence may only remain OPEN or become SEALED")
                elif previous.lifecycle is QualificationEvidenceLifecycle.SEALED:
                    if dataset.lifecycle is not QualificationEvidenceLifecycle.EVALUATED:
                        raise ValueError("SEALED evidence may only become EVALUATED")
                    if (
                        dataset.sealed_content_digest != previous.sealed_content_digest
                        or evidence_content_digest(dataset) != evidence_content_digest(previous)
                    ):
                        raise ValueError("evaluated evidence cannot alter sealed content")
                else:
                    raise ValueError("EVALUATED evidence is terminal")
            revisions.append(dataset)

    def latest_evidence(self, dataset_id: str) -> QualificationEvidenceDataset | None:
        revisions = self._evidence.get(dataset_id, ())
        return revisions[-1] if revisions else None

    def append_run(self, run: QualificationRun) -> None:
        with self._lock:
            if run.qualification_run_id in self._runs:
                raise ValueError("qualification run identity already exists")
            if any(
                item.evidence_dataset_digest == run.evidence_dataset_digest
                for item in self._runs.values()
            ):
                raise ValueError("sealed evidence dataset is already bound to another run")
            self._runs[run.qualification_run_id] = run

    def get_run(self, run_id: str) -> QualificationRun | None:
        return self._runs.get(run_id)

    def append_validity(self, assessment: QualificationValidityAssessment) -> None:
        with self._lock:
            records = self._validity[assessment.qualification_run_id]
            if any(item.assessment_id == assessment.assessment_id for item in records):
                raise ValueError("validity assessment identity already exists")
            if records and assessment.assessed_at < records[-1].assessed_at:
                raise ValueError("validity assessments must be append-only in time")
            records.append(assessment)

    def latest_validity(self, run_id: str) -> QualificationValidityAssessment | None:
        records = self._validity.get(run_id, ())
        return records[-1] if records else None

    def append_evaluation(self, evaluation: ShadowGraduationEvaluation) -> None:
        with self._lock:
            if evaluation.evaluation_id in self._evaluations:
                raise ValueError("graduation evaluation identity already exists")
            if evaluation.qualification_run_id in self._evaluation_by_run:
                raise ValueError("qualification run may be evaluated only once")
            self._evaluations[evaluation.evaluation_id] = evaluation
            self._evaluation_by_run[evaluation.qualification_run_id] = evaluation.evaluation_id

    def get_evaluation(self, evaluation_id: str) -> ShadowGraduationEvaluation | None:
        return self._evaluations.get(evaluation_id)

    def append_current_status(self, status: CurrentQualificationStatus) -> None:
        with self._lock:
            records = self._statuses[status.qualification_run_id]
            if records and status.assessed_at < records[-1].assessed_at:
                raise ValueError("current status records must be append-only in time")
            records.append(status)

    def finalize_evaluation(
        self,
        evaluated_dataset: QualificationEvidenceDataset,
        validity: QualificationValidityAssessment,
        evaluation: ShadowGraduationEvaluation,
        status: CurrentQualificationStatus,
    ) -> None:
        with self._lock:
            self.append_validity(validity)
            try:
                self.append_evaluation(evaluation)
                self.append_evidence_revision(evaluated_dataset)
                self.append_current_status(status)
            except Exception:
                validity_records = self._validity[validity.qualification_run_id]
                if validity_records and validity_records[-1] == validity:
                    validity_records.pop()
                self._evaluations.pop(evaluation.evaluation_id, None)
                self._evaluation_by_run.pop(evaluation.qualification_run_id, None)
                revisions = self._evidence.get(evaluated_dataset.dataset_id, [])
                if revisions and revisions[-1] == evaluated_dataset:
                    revisions.pop()
                raise


class SQLiteQualificationRepository(InMemoryQualificationRepository):
    """SQLite persistence with immutable rows and atomic evaluation finalization."""

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_evidence (
                dataset_id TEXT NOT NULL, revision INTEGER NOT NULL,
                record_json TEXT NOT NULL, PRIMARY KEY (dataset_id, revision))"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_runs (
                run_id TEXT PRIMARY KEY, evidence_digest TEXT NOT NULL UNIQUE,
                record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_validity (
                assessment_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                assessed_at TEXT NOT NULL, record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_evaluations (
                evaluation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m10_status (
                run_id TEXT NOT NULL, assessed_at TEXT NOT NULL,
                record_json TEXT NOT NULL, PRIMARY KEY (run_id, assessed_at))"""
            )
        self._load()

    def close(self) -> None:
        self._connection.close()

    def append_evidence_revision(self, dataset: QualificationEvidenceDataset) -> None:
        super().append_evidence_revision(dataset)
        try:
            with self._connection:
                self._insert_evidence(dataset)
        except Exception:
            self._evidence[dataset.dataset_id].pop()
            raise

    def append_run(self, run: QualificationRun) -> None:
        super().append_run(run)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m10_runs VALUES (?, ?, ?)",
                    (
                        run.qualification_run_id,
                        run.evidence_dataset_digest,
                        run.model_dump_json(),
                    ),
                )
        except Exception:
            self._runs.pop(run.qualification_run_id, None)
            raise

    def append_validity(self, assessment: QualificationValidityAssessment) -> None:
        super().append_validity(assessment)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m10_validity VALUES (?, ?, ?, ?)",
                    (
                        assessment.assessment_id,
                        assessment.qualification_run_id,
                        assessment.assessed_at.isoformat(),
                        assessment.model_dump_json(),
                    ),
                )
        except Exception:
            self._validity[assessment.qualification_run_id].pop()
            raise

    def append_evaluation(self, evaluation: ShadowGraduationEvaluation) -> None:
        super().append_evaluation(evaluation)
        try:
            with self._connection:
                self._insert_evaluation(evaluation)
        except Exception:
            self._evaluations.pop(evaluation.evaluation_id, None)
            self._evaluation_by_run.pop(evaluation.qualification_run_id, None)
            raise

    def append_current_status(self, status: CurrentQualificationStatus) -> None:
        super().append_current_status(status)
        try:
            with self._connection:
                self._insert_status(status)
        except Exception:
            self._statuses[status.qualification_run_id].pop()
            raise

    def finalize_evaluation(
        self,
        evaluated_dataset: QualificationEvidenceDataset,
        validity: QualificationValidityAssessment,
        evaluation: ShadowGraduationEvaluation,
        status: CurrentQualificationStatus,
    ) -> None:
        with self._lock:
            InMemoryQualificationRepository.append_validity(self, validity)
            try:
                InMemoryQualificationRepository.append_evaluation(self, evaluation)
                InMemoryQualificationRepository.append_evidence_revision(
                    self, evaluated_dataset
                )
                InMemoryQualificationRepository.append_current_status(self, status)
                with self._connection:
                    self._insert_validity(validity)
                    self._insert_evaluation(evaluation)
                    self._insert_evidence(evaluated_dataset)
                    self._insert_status(status)
            except Exception:
                validity_records = self._validity[validity.qualification_run_id]
                if validity_records and validity_records[-1] == validity:
                    validity_records.pop()
                self._evaluations.pop(evaluation.evaluation_id, None)
                self._evaluation_by_run.pop(evaluation.qualification_run_id, None)
                revisions = self._evidence[evaluated_dataset.dataset_id]
                if revisions and revisions[-1] == evaluated_dataset:
                    revisions.pop()
                statuses = self._statuses[status.qualification_run_id]
                if statuses and statuses[-1] == status:
                    statuses.pop()
                raise

    def _insert_evidence(self, dataset: QualificationEvidenceDataset) -> None:
        self._connection.execute(
            "INSERT INTO m10_evidence VALUES (?, ?, ?)",
            (dataset.dataset_id, dataset.revision, dataset.model_dump_json()),
        )

    def _insert_validity(self, assessment: QualificationValidityAssessment) -> None:
        self._connection.execute(
            "INSERT INTO m10_validity VALUES (?, ?, ?, ?)",
            (
                assessment.assessment_id,
                assessment.qualification_run_id,
                assessment.assessed_at.isoformat(),
                assessment.model_dump_json(),
            ),
        )

    def _insert_evaluation(self, evaluation: ShadowGraduationEvaluation) -> None:
        self._connection.execute(
            "INSERT INTO m10_evaluations VALUES (?, ?, ?)",
            (
                evaluation.evaluation_id,
                evaluation.qualification_run_id,
                evaluation.model_dump_json(),
            ),
        )

    def _insert_status(self, status: CurrentQualificationStatus) -> None:
        self._connection.execute(
            "INSERT INTO m10_status VALUES (?, ?, ?)",
            (
                status.qualification_run_id,
                status.assessed_at.isoformat(),
                status.model_dump_json(),
            ),
        )

    def _load(self) -> None:
        for row in self._connection.execute(
            "SELECT record_json FROM m10_evidence ORDER BY dataset_id, revision"
        ):
            evidence_record = QualificationEvidenceDataset.model_validate_json(row[0])
            self._evidence[evidence_record.dataset_id].append(evidence_record)
        for row in self._connection.execute("SELECT record_json FROM m10_runs"):
            run_record = QualificationRun.model_validate_json(row[0])
            self._runs[run_record.qualification_run_id] = run_record
        for row in self._connection.execute(
            "SELECT record_json FROM m10_validity ORDER BY run_id, assessed_at"
        ):
            validity_record = QualificationValidityAssessment.model_validate_json(row[0])
            self._validity[validity_record.qualification_run_id].append(validity_record)
        for row in self._connection.execute("SELECT record_json FROM m10_evaluations"):
            evaluation_record = ShadowGraduationEvaluation.model_validate_json(row[0])
            self._evaluations[evaluation_record.evaluation_id] = evaluation_record
            self._evaluation_by_run[evaluation_record.qualification_run_id] = (
                evaluation_record.evaluation_id
            )
        for row in self._connection.execute(
            "SELECT record_json FROM m10_status ORDER BY run_id, assessed_at"
        ):
            status_record = CurrentQualificationStatus.model_validate_json(row[0])
            self._statuses[status_record.qualification_run_id].append(status_record)
