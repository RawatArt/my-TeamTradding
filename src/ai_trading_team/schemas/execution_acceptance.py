"""Immutable M11 real-DEMO readiness, transport-audit, and acceptance contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    AccountReference,
    ContentDigest,
    CoreModel,
    EnvironmentReference,
    FiniteDecimal,
    Identifier,
    PositiveDecimal,
    SchemaVersion,
)
from ai_trading_team.schemas.enums import (
    DemoExecutionState,
    DemoReconciliationStatus,
    DemoSubmissionDisposition,
    ExecutionControlState,
    TradeSide,
)
from ai_trading_team.schemas.execution import DemoExecutionRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class RealDemoAcceptanceStatus(StrEnum):
    """Trusted real-DEMO acceptance result; never supplied by broker text."""

    REAL_DEMO_ACCEPTED = "REAL_DEMO_ACCEPTED"
    REAL_DEMO_REJECTED = "REAL_DEMO_REJECTED"
    REAL_DEMO_UNKNOWN = "REAL_DEMO_UNKNOWN"


class RealDemoReadinessRecord(CoreModel):
    """Finite, single-use evidence produced without claiming or dispatching."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    acceptance_run_id: Identifier
    readiness_generation_id: Identifier
    readiness_created_at: datetime
    readiness_expires_at: datetime
    candidate_id: Identifier
    candidate_digest: ContentDigest
    candidate_generation_id: Identifier
    candidate_generation_digest: ContentDigest
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    environment_acceptance_id: Identifier
    environment_acceptance_digest: ContentDigest
    policy_ref: Identifier
    policy_version: SchemaVersion
    policy_digest: ContentDigest
    execution_control_event_id: Identifier
    execution_control_event_digest: ContentDigest
    execution_control_state: Literal[ExecutionControlState.ENABLED]
    execution_snapshot_id: Identifier
    preflight_digest: ContentDigest
    checks: tuple[Identifier, ...] = Field(min_length=1)
    single_use: Literal[True] = True
    readiness_digest: ContentDigest

    _normalize_time = field_validator("readiness_created_at", "readiness_expires_at")(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.readiness_expires_at <= self.readiness_created_at:
            raise ValueError("readiness must have a finite future expiry")
        if len(set(self.checks)) != len(self.checks):
            raise ValueError("readiness checks must be unique")
        return self


class RealDemoMutationApproval(CoreModel):
    """Post-readiness human approval for one exact generation and one submission."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    mutation_approval_id: Identifier
    reviewer_ref: Identifier
    approved_at: datetime
    effective_from: datetime
    expires_at: datetime
    acceptance_run_id: Identifier
    readiness_generation_id: Identifier
    readiness_digest: ContentDigest
    readiness_created_at: datetime
    readiness_expires_at: datetime
    candidate_id: Identifier
    candidate_digest: ContentDigest
    candidate_generation_id: Identifier
    candidate_generation_digest: ContentDigest
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    environment_acceptance_id: Identifier
    environment_acceptance_digest: ContentDigest
    policy_ref: Identifier
    policy_version: SchemaVersion
    policy_digest: ContentDigest
    execution_control_event_id: Identifier
    execution_control_event_digest: ContentDigest
    execution_control_state: Literal[ExecutionControlState.ENABLED]
    submission_limit: Literal[1] = 1

    _normalize_time = field_validator(
        "approved_at",
        "effective_from",
        "expires_at",
        "readiness_created_at",
        "readiness_expires_at",
    )(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.approved_at < self.readiness_created_at:
            raise ValueError("mutation approval must be created after readiness")
        if self.approved_at > self.effective_from or self.expires_at <= self.effective_from:
            raise ValueError("mutation approval must have an ordered finite interval")
        if self.expires_at > self.readiness_expires_at:
            raise ValueError("mutation approval cannot outlive readiness")
        return self

    def applies_at(self, moment: datetime) -> bool:
        value = _utc(moment)
        return self.effective_from <= value < self.expires_at


class VendorFloatValueAudit(CoreModel):
    """Exact audit of one Decimal crossing the Python float boundary."""

    field_name: Literal["reference_price", "volume", "stop_loss", "take_profit"]
    source_decimal: PositiveDecimal
    float_repr: str = Field(min_length=1, max_length=128)
    float_hex: str = Field(min_length=1, max_length=128)
    decimal_from_float: FiniteDecimal
    decimal_from_string: FiniteDecimal
    broker_normalized_decimal: PositiveDecimal
    conversion_difference: FiniteDecimal
    broker_increment: PositiveDecimal
    policy_tolerance: PositiveDecimal
    broker_grid_aligned: Literal[True] = True
    within_policy_tolerance: Literal[True] = True


class VendorBoundaryAudit(CoreModel):
    """Sealed pre-dispatch Decimal-to-float transport evidence."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    intent_digest: ContentDigest
    audited_at: datetime
    reference_price: VendorFloatValueAudit
    volume: VendorFloatValueAudit
    stop_loss: VendorFloatValueAudit
    take_profit: VendorFloatValueAudit
    audit_digest: ContentDigest

    _normalize_time = field_validator("audited_at")(_utc)


class RealDemoAcceptanceRecord(CoreModel):
    """Sanitized trusted result derived from final execution and reconciliation state."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    acceptance_record_id: Identifier
    acceptance_run_id: Identifier
    readiness_generation_id: Identifier
    readiness_digest: ContentDigest
    mutation_approval_id: Identifier
    mutation_approval_digest: ContentDigest
    candidate_id: Identifier
    candidate_digest: ContentDigest
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    symbol: str = Field(min_length=1, max_length=64)
    side: TradeSide
    policy_digest: ContentDigest
    execution_control_event_id: Identifier
    execution_control_event_digest: ContentDigest
    status: RealDemoAcceptanceStatus
    submission_count: NonNegativeInt = Field(le=1)
    execution_record: DemoExecutionRecord
    vendor_boundary_audit: VendorBoundaryAudit | None = None
    sealed_at: datetime
    record_digest: ContentDigest

    _normalize_time = field_validator("sealed_at")(_utc)

    @model_validator(mode="after")
    def validate_trusted_result(self) -> Self:
        record = self.execution_record
        intent = record.intent
        if (
            self.account_ref != intent.account_ref
            or self.environment_ref != intent.environment_ref
            or self.symbol != intent.symbol
            or self.side is not intent.side
            or self.policy_digest != intent.execution_policy_digest
        ):
            raise ValueError("acceptance record does not match the sealed intent")
        actual_count = 1 if record.submission is not None else 0
        if self.submission_count != actual_count:
            raise ValueError("submission count must reflect the immutable execution record")
        if self.status is RealDemoAcceptanceStatus.REAL_DEMO_ACCEPTED:
            self._validate_confirmed(record)
        elif self.status is RealDemoAcceptanceStatus.REAL_DEMO_REJECTED:
            if record.state is not DemoExecutionState.REJECTED:
                raise ValueError("REAL_DEMO_REJECTED requires a terminal rejected execution")
        elif record.state not in {
            DemoExecutionState.UNKNOWN,
            DemoExecutionState.RECONCILIATION_FAILED,
        }:
            raise ValueError("REAL_DEMO_UNKNOWN requires uncertain reconciliation state")
        return self

    def _validate_confirmed(self, record: DemoExecutionRecord) -> None:
        from ai_trading_team.execution.vendor_boundary import verify_vendor_boundary_audit

        intent = record.intent
        reconciliation = record.reconciliation
        if (
            self.submission_count != 1
            or record.state is not DemoExecutionState.CONFIRMED
            or reconciliation is None
            or reconciliation.status is not DemoReconciliationStatus.CONFIRMED
            or len(reconciliation.evidence) != 1
            or record.submission is None
            or self.vendor_boundary_audit is None
        ):
            raise ValueError("REAL_DEMO_ACCEPTED requires one confirmed reconciled submission")
        evidence = reconciliation.evidence[0]
        submission = record.submission
        assert submission is not None
        exact = (
            submission.execution_intent_id == intent.execution_intent_id,
            submission.intent_digest == intent.intent_digest,
            submission.disposition is DemoSubmissionDisposition.ACCEPTED,
            reconciliation.execution_intent_id == intent.execution_intent_id,
            reconciliation.intent_digest == intent.intent_digest,
            evidence.account_ref == intent.account_ref,
            evidence.environment_ref == intent.environment_ref,
            evidence.symbol == intent.symbol,
            evidence.side is intent.side,
            evidence.volume == intent.volume,
            evidence.dispatch_started_at >= submission.dispatch_started_at,
            evidence.dispatch_completed_at <= evidence.observed_at,
            evidence.broker_order_id is not None or evidence.broker_deal_id is not None,
            evidence.stop_loss == intent.stop_loss,
            evidence.take_profit == intent.take_profit,
            evidence.resulting_position_id is not None,
            evidence.fill_price is not None,
        )
        if not all(exact):
            raise ValueError("confirmed broker position is incompatible with approved intent")
        audit = self.vendor_boundary_audit
        assert audit is not None
        audit_matches = (
            audit.execution_intent_id == intent.execution_intent_id,
            audit.intent_digest == intent.intent_digest,
            audit.reference_price.source_decimal == intent.reference_price,
            audit.volume.source_decimal == intent.volume,
            audit.stop_loss.source_decimal == intent.stop_loss,
            audit.take_profit.source_decimal == intent.take_profit,
            audit.reference_price.broker_normalized_decimal == intent.reference_price,
            audit.volume.broker_normalized_decimal == intent.volume,
            audit.stop_loss.broker_normalized_decimal == intent.stop_loss,
            audit.take_profit.broker_normalized_decimal == intent.take_profit,
            verify_vendor_boundary_audit(audit),
        )
        if not all(audit_matches):
            raise ValueError("vendor-boundary audit does not match the sealed intent")
        assert evidence.fill_price is not None
        adverse = (
            evidence.fill_price > intent.risk_validation_price
            if intent.side is TradeSide.BUY
            else evidence.fill_price < intent.risk_validation_price
        )
        if adverse:
            raise ValueError("confirmed broker fill is outside reviewed risk policy")
