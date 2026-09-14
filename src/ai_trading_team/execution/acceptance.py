"""Deterministic qualification, operator, and DEMO-environment gates."""

from datetime import UTC, datetime

from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    ExecutionControlState,
    GraduationDisposition,
    ModelProvider,
    QualificationEvidenceValidity,
)
from ai_trading_team.schemas.execution import (
    DemoExecutionApproval,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPolicy,
    QualifiedDemoExecutionCandidate,
)


def validate_execution_authority(
    candidate: QualifiedDemoExecutionCandidate,
    acceptance: DemoExecutionEnvironmentAcceptance,
    approval: DemoExecutionApproval,
    policy: DemoExecutionPolicy,
    *,
    control_state: ExecutionControlState,
    approval_revoked: bool,
    evaluated_at: datetime,
) -> None:
    """Fail closed unless every non-broker authorization remains current and exact."""
    now = _utc(evaluated_at)
    status = candidate.qualification_status
    validity = status.validity_assessment
    manifest = candidate.dependency_manifest
    decision = candidate.decision

    if control_state is not ExecutionControlState.ENABLED:
        category = {
            ExecutionControlState.DISABLED: DemoExecutionFailureCategory.EXECUTION_DISABLED,
            ExecutionControlState.PAUSED: DemoExecutionFailureCategory.EXECUTION_PAUSED,
            ExecutionControlState.HALTED: DemoExecutionFailureCategory.EXECUTION_HALTED,
        }[control_state]
        raise _error(category, "DEMO execution control is not enabled")
    if status.graduation_disposition is not GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW:
        raise _error(
            DemoExecutionFailureCategory.QUALIFICATION_INELIGIBLE,
            "qualification did not pass human DEMO-review eligibility",
        )
    if validity.state is not QualificationEvidenceValidity.VALID:
        raise _error(
            DemoExecutionFailureCategory.QUALIFICATION_EVIDENCE_INVALID,
            "qualification evidence is not currently valid",
        )
    if validity.assessed_at > now or validity.valid_until is None or now >= validity.valid_until:
        raise _error(
            DemoExecutionFailureCategory.QUALIFICATION_EVIDENCE_INVALID,
            "qualification validity window is not current",
        )
    if candidate.dependency_manifest_digest != content_digest(manifest) or (
        validity.dependency_manifest_digest != candidate.dependency_manifest_digest
    ):
        raise _error(
            DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
            "qualified material generation digest is incompatible",
        )
    if candidate.qualification_status_digest != content_digest(status):
        raise _error(
            DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
            "qualification status digest is incompatible",
        )
    if any(item.provider is ModelProvider.FAKE for item in manifest.assignments):
        raise _error(
            DemoExecutionFailureCategory.FAKE_PROVIDER_EVIDENCE,
            "fake-provider evidence cannot authorize DEMO execution",
        )
    if any(
        item.acceptance_valid_until is None or now >= item.acceptance_valid_until
        for item in manifest.assignments
    ):
        raise _error(
            DemoExecutionFailureCategory.ACCEPTANCE_CHAIN_INVALID,
            "one or more real-provider acceptance records are absent or expired",
        )
    timestamp_acceptance = manifest.symbol_timestamp_acceptance
    if now >= timestamp_acceptance.expires_at or timestamp_acceptance.symbol != decision.symbol:
        raise _error(
            DemoExecutionFailureCategory.TIMESTAMP_SEMANTICS_INVALID,
            "symbol timestamp acceptance is absent, expired, or incompatible",
        )
    policy_digest = content_digest(policy)
    if acceptance.execution_policy_digest != policy_digest:
        raise _error(
            DemoExecutionFailureCategory.ENVIRONMENT_MISMATCH,
            "environment acceptance does not bind the current execution policy",
        )
    if now >= acceptance.expires_at:
        raise _error(
            DemoExecutionFailureCategory.ENVIRONMENT_ACCEPTANCE_EXPIRED,
            "DEMO environment acceptance has expired",
        )
    if acceptance.symbol != decision.symbol:
        raise _error(
            DemoExecutionFailureCategory.SYMBOL_MISMATCH,
            "accepted DEMO symbol differs from the qualified decision symbol",
        )
    if approval_revoked:
        raise _error(
            DemoExecutionFailureCategory.APPROVAL_REVOKED,
            "human DEMO approval has been revoked",
        )
    if not approval.applies_at(now):
        raise _error(
            DemoExecutionFailureCategory.APPROVAL_EXPIRED,
            "human DEMO approval is not effective",
        )
    shadow = decision.shadow_record
    if shadow is None or shadow.shadow_trade_intent is None:
        raise _error(
            DemoExecutionFailureCategory.QUALIFICATION_INELIGIBLE,
            "qualified decision has no immutable SHADOW intent",
        )
    shadow_intent = shadow.shadow_trade_intent
    expected = (
        approval.candidate_id == candidate.candidate_id,
        approval.source_decision_record_digest == content_digest(decision),
        approval.source_shadow_intent_digest == content_digest(shadow_intent),
        approval.analysis_proposal_digest == content_digest(shadow_intent.proposal),
        approval.analysis_risk_decision_digest == content_digest(shadow_intent.risk_decision),
        approval.qualification_run_id == status.qualification_run_id,
        approval.qualification_status_digest == candidate.qualification_status_digest,
        approval.generation_id == manifest.generation_id,
        approval.generation_digest == candidate.dependency_manifest_digest,
        approval.environment_acceptance_id == acceptance.acceptance_id,
        approval.environment_acceptance_digest == content_digest(acceptance),
        approval.account_ref == acceptance.account_ref,
        approval.environment_ref == acceptance.environment_ref,
        approval.symbol == acceptance.symbol,
        approval.execution_policy_digest == policy_digest,
    )
    if not all(expected):
        raise _error(
            DemoExecutionFailureCategory.APPROVAL_MISSING,
            "human approval does not exactly authorize this generation and environment",
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error(DemoExecutionFailureCategory.UNKNOWN, "evaluation time must be aware")
    return value.astimezone(UTC)


def _error(category: DemoExecutionFailureCategory, message: str) -> DemoExecutionError:
    return DemoExecutionError(category, message)
