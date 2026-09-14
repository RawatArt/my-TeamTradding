"""Current M10 dependency and evidence-validity assessment."""

from datetime import datetime

from ai_trading_team.qualification.errors import QualificationError
from ai_trading_team.qualification.evidence import verify_sealed_evidence
from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    ModelProvider,
    QualificationErrorCategory,
    QualificationEvidenceValidity,
)
from ai_trading_team.schemas.qualification import (
    QualificationArtifactReference,
    QualificationDependencyManifest,
    QualificationEvidenceDataset,
    QualificationRun,
    QualificationValidityAssessment,
)


def dependency_manifest_digest(manifest: QualificationDependencyManifest) -> str:
    return content_digest(manifest)


def artifact_reference(
    artifact_type: str,
    artifact_id: str,
    artifact: object,
    *,
    schema_version: str = "1.0.0",
) -> QualificationArtifactReference:
    return QualificationArtifactReference(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        schema_version=schema_version,
        content_digest=content_digest(artifact),
    )


def assess_validity(
    run: QualificationRun,
    dataset: QualificationEvidenceDataset,
    current_manifest: QualificationDependencyManifest,
    *,
    assessed_at: datetime,
    invalidation_reasons: tuple[str, ...] = (),
    contaminated: bool = False,
) -> QualificationValidityAssessment:
    verify_sealed_evidence(dataset)
    if (
        run.evidence_dataset_id != dataset.dataset_id
        or run.evidence_dataset_digest != dataset.sealed_content_digest
        or run.qualification_run_id != dataset.qualification_run_id
    ):
        raise QualificationError(
            QualificationErrorCategory.INVALID_EVIDENCE,
            "qualification run and sealed evidence do not match",
        )
    declared = dependency_manifest_digest(run.dependency_manifest)
    current = dependency_manifest_digest(current_manifest)
    evidence = (
        artifact_reference(
            "qualification_dependency_manifest",
            run.dependency_manifest.generation_id,
            run.dependency_manifest,
        ),
        artifact_reference(
            "symbol_timestamp_acceptance",
            current_manifest.symbol_timestamp_acceptance.acceptance_id,
            current_manifest.symbol_timestamp_acceptance,
        ),
    )
    expiry_candidates = [current_manifest.symbol_timestamp_acceptance.expires_at]
    expiry_candidates.extend(
        item.acceptance_valid_until
        for item in current_manifest.assignments
        if item.provider is not ModelProvider.FAKE and item.acceptance_valid_until is not None
    )
    valid_until = min(expiry_candidates)
    dependency_reasons = _evidence_dependency_reasons(dataset, current_manifest)
    reasons: tuple[str, ...]
    if contaminated:
        state = QualificationEvidenceValidity.CONTAMINATED
        reasons = ("sealed evidence was used for a material system change",)
    elif invalidation_reasons:
        state = QualificationEvidenceValidity.INVALIDATED
        reasons = invalidation_reasons
    elif dependency_reasons:
        state = QualificationEvidenceValidity.INVALIDATED
        reasons = dependency_reasons
    elif (
        declared != run.dependency_manifest_digest
        or current != run.dependency_manifest_digest
        or current_manifest.generation_id != run.dependency_manifest.generation_id
    ):
        state = QualificationEvidenceValidity.INVALIDATED
        reasons = ("current material dependencies differ from the qualified generation",)
    elif assessed_at >= valid_until:
        state = QualificationEvidenceValidity.EXPIRED
        reasons = ("one or more required acceptance artifacts expired",)
    else:
        state = QualificationEvidenceValidity.VALID
        reasons = ()
    identity_payload = {
        "run_id": run.qualification_run_id,
        "dataset_digest": dataset.sealed_content_digest,
        "manifest_digest": current,
        "state": state.value,
        "assessed_at": assessed_at,
        "reasons": reasons,
    }
    return QualificationValidityAssessment(
        assessment_id=deterministic_id("qualification-validity", identity_payload),
        qualification_run_id=run.qualification_run_id,
        evidence_dataset_id=dataset.dataset_id,
        evidence_dataset_digest=dataset.sealed_content_digest,
        dependency_manifest_digest=current,
        state=state,
        assessed_at=assessed_at,
        valid_until=(
            valid_until
            if state
            in {
                QualificationEvidenceValidity.VALID,
                QualificationEvidenceValidity.EXPIRED,
            }
            else None
        ),
        reasons=reasons,
        evidence=evidence,
    )


def _evidence_dependency_reasons(
    dataset: QualificationEvidenceDataset,
    manifest: QualificationDependencyManifest,
) -> tuple[str, ...]:
    """Return deterministic incompatibilities between evidence and its generation."""
    reasons: list[str] = []
    if (
        dataset.generation_id != manifest.generation_id
        or dataset.generation_digest != dependency_manifest_digest(manifest)
    ):
        reasons.append("sealed evidence generation differs from the dependency manifest")

    assignments = {item.role: item for item in manifest.assignments}
    for decision in dataset.decisions:
        view = decision.agent_market_view
        if view is not None:
            if view.schema_version != manifest.agent_market_view_version:
                reasons.append("AgentMarketView version differs from the qualified generation")
            if view.features is None:
                reasons.append("qualification decision lacks its feature projection")
            else:
                if view.features.allowlist_version != manifest.feature_allowlist_version:
                    reasons.append("AgentFeatureView allowlist version differs")
                if view.features.source_feature_engine_version != manifest.feature_engine_version:
                    reasons.append("feature engine version differs from the qualified generation")
        if decision.shadow_record is None:
            continue
        for invocation in decision.shadow_record.decision_cycle.invocations:
            trace = invocation.trace
            assignment = assignments.get(trace.agent_role.value)
            if assignment is None:
                reasons.append(
                    f"missing qualified role assignment for {trace.agent_role.value}"
                )
                continue
            observed = (
                trace.provider,
                trace.model_identifier,
                trace.agent_version,
                trace.prompt_id,
                trace.prompt_version,
                trace.prompt_digest,
                trace.runtime_profile_ref,
            )
            expected = (
                assignment.provider,
                assignment.model_identifier,
                assignment.agent_version,
                assignment.prompt_id,
                assignment.prompt_version,
                assignment.prompt_digest,
                assignment.runtime_profile_ref,
            )
            if observed != expected:
                reasons.append(
                    "invocation identity differs from qualified assignment for "
                    f"{trace.agent_role.value}"
                )

    declared_pricing = {
        item.artifact_id: item.content_digest for item in manifest.pricing_profile_refs
    }
    observed_pricing = {
        item.profile_ref: content_digest(item) for item in dataset.pricing_profiles
    }
    if declared_pricing != observed_pricing:
        reasons.append("sealed pricing profiles differ from the dependency manifest")
    if any(
        outcome.evaluator_version != manifest.outcome_policy_version
        for outcome in dataset.outcomes
    ):
        reasons.append("outcome evaluator version differs from the qualified generation")
    return tuple(sorted(set(reasons)))
