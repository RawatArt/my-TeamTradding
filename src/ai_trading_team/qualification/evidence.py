"""Append-only OPEN -> SEALED -> EVALUATED qualification evidence transitions."""

from datetime import datetime

from ai_trading_team.qualification.errors import QualificationError
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    QualificationErrorCategory,
    QualificationEvidenceLifecycle,
)
from ai_trading_team.schemas.evaluation import TradeOutcome
from ai_trading_team.schemas.observation import ContinuousDecisionRecord, DecisionCandleClaim
from ai_trading_team.schemas.qualification import (
    QualificationArtifactReference,
    QualificationEvidenceDataset,
    QualificationIncident,
)
from ai_trading_team.schemas.runtime import PricingProfile


def evidence_content_digest(dataset: QualificationEvidenceDataset) -> str:
    """Hash only sealed identity and evidence, excluding revision/lifecycle metadata."""
    return content_digest(
        {
            "canonicalization_version": "1.0.0",
            "schema_version": dataset.schema_version,
            "dataset_id": dataset.dataset_id,
            "qualification_run_id": dataset.qualification_run_id,
            "generation_id": dataset.generation_id,
            "generation_digest": dataset.generation_digest,
            "partition": dataset.partition,
            "opened_at": dataset.opened_at,
            "claims": dataset.claims,
            "decisions": dataset.decisions,
            "outcomes": dataset.outcomes,
            "pricing_profiles": dataset.pricing_profiles,
            "incidents": dataset.incidents,
            "safety_evidence": dataset.safety_evidence,
        }
    )


def append_evidence(
    dataset: QualificationEvidenceDataset,
    *,
    claims: tuple[DecisionCandleClaim, ...] = (),
    decisions: tuple[ContinuousDecisionRecord, ...] = (),
    outcomes: tuple[TradeOutcome, ...] = (),
    pricing_profiles: tuple[PricingProfile, ...] = (),
    incidents: tuple[QualificationIncident, ...] = (),
    safety_evidence: tuple[QualificationArtifactReference, ...] = (),
) -> QualificationEvidenceDataset:
    if dataset.lifecycle is not QualificationEvidenceLifecycle.OPEN:
        raise QualificationError(
            QualificationErrorCategory.EVIDENCE_NOT_OPEN,
            "sealed or evaluated evidence cannot be changed or backfilled",
        )
    updated = dataset.model_copy(
        update={
            "revision": dataset.revision + 1,
            "previous_revision_digest": content_digest(dataset),
            "claims": tuple(sorted((*dataset.claims, *claims), key=lambda item: item.decision_key)),
            "decisions": tuple(
                sorted((*dataset.decisions, *decisions), key=lambda item: item.decision_key)
            ),
            "outcomes": tuple(
                sorted((*dataset.outcomes, *outcomes), key=lambda item: item.outcome_id)
            ),
            "pricing_profiles": tuple(
                sorted(
                    (*dataset.pricing_profiles, *pricing_profiles),
                    key=lambda item: item.profile_ref,
                )
            ),
            "incidents": tuple(
                sorted((*dataset.incidents, *incidents), key=lambda item: item.incident_id)
            ),
            "safety_evidence": tuple(
                sorted(
                    (*dataset.safety_evidence, *safety_evidence),
                    key=lambda item: item.artifact_id,
                )
            ),
        }
    )
    return QualificationEvidenceDataset.model_validate(updated.model_dump())


def seal_evidence(
    dataset: QualificationEvidenceDataset, *, sealed_at: datetime
) -> QualificationEvidenceDataset:
    if dataset.lifecycle is not QualificationEvidenceLifecycle.OPEN:
        raise QualificationError(
            QualificationErrorCategory.EVIDENCE_NOT_OPEN,
            "only open qualification evidence may be sealed",
        )
    digest = evidence_content_digest(dataset)
    sealed = dataset.model_copy(
        update={
            "lifecycle": QualificationEvidenceLifecycle.SEALED,
            "revision": dataset.revision + 1,
            "previous_revision_digest": content_digest(dataset),
            "sealed_at": sealed_at,
            "sealed_content_digest": digest,
        }
    )
    return QualificationEvidenceDataset.model_validate(sealed.model_dump())


def mark_evaluated(
    dataset: QualificationEvidenceDataset,
    evaluation: QualificationArtifactReference,
    *,
    evaluated_at: datetime,
) -> QualificationEvidenceDataset:
    verify_sealed_evidence(dataset)
    if dataset.lifecycle is not QualificationEvidenceLifecycle.SEALED:
        raise QualificationError(
            QualificationErrorCategory.EVIDENCE_NOT_SEALED,
            "only sealed, unevaluated evidence may transition to evaluated",
        )
    updated = dataset.model_copy(
        update={
            "lifecycle": QualificationEvidenceLifecycle.EVALUATED,
            "revision": dataset.revision + 1,
            "previous_revision_digest": content_digest(dataset),
            "evaluated_at": evaluated_at,
            "evaluation_reference": evaluation,
        }
    )
    return QualificationEvidenceDataset.model_validate(updated.model_dump())


def verify_sealed_evidence(dataset: QualificationEvidenceDataset) -> None:
    if dataset.lifecycle not in {
        QualificationEvidenceLifecycle.SEALED,
        QualificationEvidenceLifecycle.EVALUATED,
    }:
        raise QualificationError(
            QualificationErrorCategory.EVIDENCE_NOT_SEALED,
            "graduation requires sealed evidence",
        )
    if dataset.sealed_content_digest != evidence_content_digest(dataset):
        raise QualificationError(
            QualificationErrorCategory.DIGEST_MISMATCH,
            "sealed qualification evidence digest is invalid",
        )

