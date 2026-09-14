"""Read-only extraction of bounded evidence from the accepted M9 repository."""

from ai_trading_team.qualification.evidence import append_evidence
from ai_trading_team.schemas.evaluation import TradeOutcome
from ai_trading_team.schemas.qualification import (
    QualificationArtifactReference,
    QualificationEvidenceDataset,
    QualificationIncident,
)
from ai_trading_team.schemas.runtime import PricingProfile
from ai_trading_team.storage.observation import ObservationRepository


def collect_m9_evidence(
    dataset: QualificationEvidenceDataset,
    source: ObservationRepository,
    *,
    outcomes: tuple[TradeOutcome, ...] = (),
    pricing_profiles: tuple[PricingProfile, ...] = (),
    incidents: tuple[QualificationIncident, ...] = (),
    safety_evidence: tuple[QualificationArtifactReference, ...] = (),
) -> QualificationEvidenceDataset:
    """Copy only the predeclared evaluation interval; never poll or start M9."""
    partition = dataset.partition.partition
    claims = source.claims_in_range(
        started_at=partition.evaluation_start,
        ended_at=partition.evaluation_end,
    )
    decisions = source.decisions_in_range(
        started_at=partition.evaluation_start,
        ended_at=partition.evaluation_end,
    )
    return append_evidence(
        dataset,
        claims=claims,
        decisions=decisions,
        outcomes=outcomes,
        pricing_profiles=pricing_profiles,
        incidents=incidents,
        safety_evidence=safety_evidence,
    )

