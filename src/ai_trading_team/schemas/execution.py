"""Immutable M11 DEMO execution, approval, and audit contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    AccountReference,
    ContentDigest,
    CoreModel,
    CycleId,
    EnvironmentReference,
    Identifier,
    NonNegativeDecimal,
    PositiveDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    DemoExecutionFailureCategory,
    DemoExecutionState,
    DemoFillingMode,
    DemoOrderExecutionMode,
    DemoReconciliationStatus,
    DemoSubmissionDisposition,
    ExecutionControlState,
    ExecutionSnapshotPurpose,
    ModelProvider,
    QualificationEvidenceValidity,
    TradeSide,
)
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5TerminalHealth,
    MT5Tick,
)
from ai_trading_team.schemas.observation import ContinuousDecisionRecord, RiskContextEvidence
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationDependencyManifest,
)
from ai_trading_team.schemas.risk import RiskDecision


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class DemoExecutionEnvironmentAcceptance(CoreModel):
    """Finite acceptance of one exact DEMO account and terminal environment."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    acceptance_id: Identifier
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    account_mode: Literal[BrokerAccountMode.DEMO] = BrokerAccountMode.DEMO
    symbol: Symbol
    package_version: str = Field(min_length=1, max_length=128)
    terminal_version: str = Field(min_length=1, max_length=128)
    terminal_build: NonNegativeInt
    adapter_version: SchemaVersion
    symbol_capability_digest: ContentDigest
    execution_policy_digest: ContentDigest
    evidence_ref: Identifier
    evidence_digest: ContentDigest
    accepted_at: datetime
    expires_at: datetime
    accepted: Literal[True] = True

    _normalize_time = field_validator("accepted_at", "expires_at")(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.expires_at <= self.accepted_at:
            raise ValueError("DEMO environment acceptance must have a finite future expiry")
        return self


class DemoExecutionApproval(CoreModel):
    """Immutable human approval for one exact qualified generation and environment."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    approval_id: Identifier
    reviewer_ref: Identifier
    candidate_id: Identifier
    source_decision_record_digest: ContentDigest
    source_shadow_intent_digest: ContentDigest
    analysis_proposal_digest: ContentDigest
    analysis_risk_decision_digest: ContentDigest
    qualification_run_id: Identifier
    qualification_status_digest: ContentDigest
    generation_id: Identifier
    generation_digest: ContentDigest
    environment_acceptance_id: Identifier
    environment_acceptance_digest: ContentDigest
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    symbol: Symbol
    execution_policy_digest: ContentDigest
    effective_from: datetime
    expires_at: datetime
    approved_at: datetime

    _normalize_time = field_validator("effective_from", "expires_at", "approved_at")(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.approved_at > self.effective_from or self.expires_at <= self.effective_from:
            raise ValueError("approval timestamps must define an ordered finite interval")
        return self

    def applies_at(self, moment: datetime) -> bool:
        value = _utc(moment)
        return self.effective_from <= value < self.expires_at


class DemoExecutionApprovalRevocation(CoreModel):
    """Append-only operator revocation; an approval is never edited in place."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    revocation_id: Identifier
    approval_id: Identifier
    approval_digest: ContentDigest
    reviewer_ref: Identifier
    revoked_at: datetime
    reason: str = Field(min_length=1, max_length=512)

    _normalize_time = field_validator("revoked_at")(_utc)


class DemoExecutionPolicy(CoreModel):
    """Reviewed deterministic limits for the first DEMO-only market order."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_ref: Identifier
    policy_version: SchemaVersion
    maximum_tick_age_seconds: PositiveInt = 5
    maximum_decision_age_seconds: PositiveInt = 300
    maximum_preflight_seconds: PositiveInt = 15
    intent_ttl_seconds: PositiveInt = 10
    maximum_spread_ticks: PositiveDecimal
    maximum_price_drift_ticks: NonNegativeDecimal
    maximum_adverse_slippage_ticks: NonNegativeDecimal
    supported_execution_modes: frozenset[DemoOrderExecutionMode] = Field(min_length=1)
    filling_mode: DemoFillingMode
    maximum_account_positions_before_dispatch: Literal[0] = 0
    maximum_symbol_positions_before_dispatch: Literal[0] = 0
    require_initial_stop_loss: Literal[True] = True
    require_initial_take_profit: Literal[True] = True
    exact_volume_match_required: Literal[True] = True
    magic: PositiveInt
    comment_prefix: str = Field(min_length=1, max_length=12, pattern=r"^[A-Za-z0-9_-]+$")


class DemoSymbolExecutionCapabilities(CoreModel):
    """Execution-only normalized capabilities bound to accepted M1 symbol metadata."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    symbol: Symbol
    observed_at: datetime
    symbol_info_digest: ContentDigest
    execution_mode: DemoOrderExecutionMode
    filling_modes: frozenset[DemoFillingMode] = Field(min_length=1)
    market_order_allowed: bool
    stop_loss_allowed: bool
    take_profit_allowed: bool

    _normalize_time = field_validator("observed_at")(_utc)


class ExecutionSnapshotLink(CoreModel):
    """Explicitly separates immutable analysis facts from pre-send revalidation."""

    analysis_snapshot_id: SnapshotId
    execution_snapshot_id: SnapshotId
    purpose: Literal[ExecutionSnapshotPurpose.PRE_SEND_REVALIDATION] = (
        ExecutionSnapshotPurpose.PRE_SEND_REVALIDATION
    )

    @model_validator(mode="after")
    def require_distinct_snapshots(self) -> Self:
        if self.analysis_snapshot_id == self.execution_snapshot_id:
            raise ValueError("analysis and execution-revalidation snapshots must be distinct")
        return self


class QualifiedDemoExecutionCandidate(CoreModel):
    """Exact M9 shadow decision plus current M10 qualification authority."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: Identifier
    decision: ContinuousDecisionRecord
    qualification_status: CurrentQualificationStatus
    dependency_manifest: QualificationDependencyManifest
    dependency_manifest_digest: ContentDigest
    qualification_status_digest: ContentDigest

    @model_validator(mode="after")
    def validate_authority_shape(self) -> Self:
        if not self.qualification_status.currently_eligible_for_demo_review:
            raise ValueError("candidate requires current eligibility for DEMO review")
        if (
            self.qualification_status.validity_assessment.state
            is not QualificationEvidenceValidity.VALID
        ):
            raise ValueError("candidate qualification evidence must currently be valid")
        if self.qualification_status.qualification_run_id != (
            self.qualification_status.validity_assessment.qualification_run_id
        ):
            raise ValueError("qualification status trace is inconsistent")
        if any(
            item.provider is ModelProvider.FAKE
            for item in self.dependency_manifest.assignments
        ):
            raise ValueError("fake-provider qualification cannot authorize DEMO execution")
        record = self.decision
        shadow = record.shadow_record
        if shadow is None or shadow.shadow_trade_intent is None:
            raise ValueError("candidate requires an approved persisted shadow trade intent")
        if record.actual_snapshot_id is None:
            raise ValueError("candidate requires the authoritative analysis snapshot identity")
        if shadow.decision_cycle.initial_snapshot_id != record.actual_snapshot_id:
            raise ValueError("shadow record must retain the authoritative analysis snapshot")
        return self


class FreshExecutionObservation(CoreModel):
    """Read-only facts captured solely for pre-send validation."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    captured_at: datetime
    environment_ref: EnvironmentReference
    snapshot: MarketSnapshot
    risk_context_evidence: RiskContextEvidence
    account_positions: tuple[MT5OpenPosition, ...]
    capabilities: DemoSymbolExecutionCapabilities

    _normalize_time = field_validator("captured_at")(_utc)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        context = self.risk_context_evidence.context
        if (
            context.cycle_id != self.snapshot.cycle_id
            or context.snapshot_id != self.snapshot.snapshot_id
        ):
            raise ValueError("fresh account context must match the execution snapshot")
        if context.account_open_position_count != len(self.account_positions):
            raise ValueError("fresh account context must count the supplied account positions")
        if self.capabilities.symbol != self.snapshot.symbol:
            raise ValueError("execution capabilities must match the snapshot symbol")
        if self.captured_at < self.snapshot.snapshot_completed_at:
            raise ValueError("capture completion cannot predate the execution snapshot")
        return self


class FreshRiskRevalidation(CoreModel):
    """Trusted M3 result for the distinct execution-validation snapshot."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_link: ExecutionSnapshotLink
    original_proposal_id: Identifier
    original_proposal_digest: ContentDigest
    original_risk_decision_digest: ContentDigest
    revalidation_proposal: TradeProposal
    revalidation_proposal_digest: ContentDigest
    risk_decision: RiskDecision
    risk_decision_digest: ContentDigest
    evaluated_at: datetime

    _normalize_time = field_validator("evaluated_at")(_utc)

    @model_validator(mode="after")
    def validate_linkage(self) -> Self:
        proposal = self.revalidation_proposal
        decision = self.risk_decision
        if (
            proposal.snapshot_id != self.snapshot_link.execution_snapshot_id
            or decision.snapshot_id != self.snapshot_link.execution_snapshot_id
            or decision.proposal_id != proposal.proposal_id
            or decision.cycle_id != proposal.cycle_id
            or decision.symbol != proposal.symbol
        ):
            raise ValueError("fresh proposal and Risk decision linkage must match")
        return self


class DemoExecutionPreflight(CoreModel):
    """Persisted deterministic price, timing, capability, and position checks."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_link: ExecutionSnapshotLink
    started_at: datetime
    completed_at: datetime
    reference_price: PositiveDecimal
    risk_validation_price: PositiveDecimal
    spread_ticks: NonNegativeDecimal
    price_drift_ticks: NonNegativeDecimal
    maximum_deviation_points: NonNegativeInt
    execution_mode: DemoOrderExecutionMode
    passed: bool
    failure: DemoExecutionFailure | None = None

    _normalize_time = field_validator("started_at", "completed_at")(_utc)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("preflight completion cannot predate its start")
        if self.passed == (self.failure is not None):
            raise ValueError("preflight failure metadata must match its result")
        return self


class DemoOrderIntent(CoreModel):
    """Sealed, non-editable instruction for at most one protected DEMO order attempt."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    client_trade_id: Identifier
    cycle_id: CycleId
    snapshot_link: ExecutionSnapshotLink
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    symbol: Symbol
    side: TradeSide
    volume: PositiveDecimal
    reference_price: PositiveDecimal
    risk_validation_price: PositiveDecimal
    stop_loss: PositiveDecimal
    take_profit: PositiveDecimal
    maximum_deviation_points: NonNegativeInt
    execution_mode: DemoOrderExecutionMode
    filling_mode: DemoFillingMode
    magic: PositiveInt
    comment: str = Field(min_length=1, max_length=31)
    source_decision_record_digest: ContentDigest
    source_shadow_intent_digest: ContentDigest
    analysis_proposal_id: Identifier
    analysis_proposal_digest: ContentDigest
    analysis_risk_decision_digest: ContentDigest
    revalidation_proposal_id: Identifier
    revalidation_proposal_digest: ContentDigest
    revalidation_risk_decision_digest: ContentDigest
    qualification_run_id: Identifier
    qualification_status_digest: ContentDigest
    generation_id: Identifier
    generation_digest: ContentDigest
    environment_acceptance_id: Identifier
    environment_acceptance_digest: ContentDigest
    approval_id: Identifier
    approval_digest: ContentDigest
    execution_policy_digest: ContentDigest
    created_at: datetime
    expires_at: datetime
    intent_digest: ContentDigest

    _normalize_time = field_validator("created_at", "expires_at")(_utc)

    @model_validator(mode="after")
    def validate_protected_geometry(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("sealed intent must have a finite future expiry")
        if self.side is TradeSide.BUY and not (
            self.stop_loss < self.risk_validation_price < self.take_profit
        ):
            raise ValueError("BUY intent requires stop < risk price < target")
        if self.side is TradeSide.SELL and not (
            self.take_profit < self.risk_validation_price < self.stop_loss
        ):
            raise ValueError("SELL intent requires target < risk price < stop")
        return self


class DemoExecutionFailure(CoreModel):
    code: DemoExecutionFailureCategory
    sanitized_detail: str = Field(min_length=1, max_length=512)


class DemoOrderCheckResult(CoreModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    intent_digest: ContentDigest
    checked_at: datetime
    accepted: bool
    broker_code: int | None = None
    sanitized_detail: str = Field(min_length=1, max_length=512)

    _normalize_time = field_validator("checked_at")(_utc)


class FinalDispatchObservation(CoreModel):
    """Last read-only terminal state captured immediately before mutation."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    observed_at: datetime
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    health: MT5TerminalHealth
    account: MT5AccountInfo
    symbol_info: MT5SymbolInfo
    capabilities: DemoSymbolExecutionCapabilities
    tick: MT5Tick
    positions: tuple[MT5OpenPosition, ...]

    _normalize_time = field_validator("observed_at")(_utc)

    @model_validator(mode="after")
    def validate_symbol_scope(self) -> Self:
        if self.symbol_info.symbol != self.tick.symbol or (
            self.capabilities.symbol != self.tick.symbol
        ):
            raise ValueError("final dispatch symbol observations must match")
        if self.observed_at < max(
            self.health.retrieved_at,
            self.account.retrieved_at,
            self.symbol_info.retrieved_at,
            self.tick.retrieved_at,
        ):
            raise ValueError("final observation time cannot predate its source reads")
        return self


class FinalDispatchGuardResult(CoreModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    evaluated_at: datetime
    passed: bool
    checks: tuple[Identifier, ...] = Field(min_length=1)
    failure: DemoExecutionFailure | None = None

    _normalize_time = field_validator("evaluated_at")(_utc)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.passed == (self.failure is not None):
            raise ValueError("guard failure metadata must match the result")
        return self


class CompositeBrokerEvidence(CoreModel):
    """Broker proof that never relies on magic or comment alone."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    account_ref: AccountReference
    environment_ref: EnvironmentReference
    symbol: Symbol
    side: TradeSide
    volume: PositiveDecimal
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    observed_at: datetime
    client_trade_reference: Identifier | None = None
    broker_order_id: PositiveInt | None = None
    broker_deal_id: PositiveInt | None = None
    resulting_position_id: PositiveInt | None = None
    fill_price: PositiveDecimal | None = None
    stop_loss: PositiveDecimal | None = None
    take_profit: PositiveDecimal | None = None
    magic: int | None = None
    comment: str | None = Field(default=None, max_length=128)

    _normalize_time = field_validator(
        "dispatch_started_at", "dispatch_completed_at", "observed_at"
    )(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if not self.dispatch_started_at <= self.dispatch_completed_at <= self.observed_at:
            raise ValueError("broker evidence timestamps must be ordered")
        return self


class DemoSubmissionReceipt(CoreModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    intent_digest: ContentDigest
    disposition: DemoSubmissionDisposition
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    broker_code: int | None = None
    evidence: CompositeBrokerEvidence | None = None
    sanitized_detail: str = Field(min_length=1, max_length=512)

    _normalize_time = field_validator("dispatch_started_at", "dispatch_completed_at")(_utc)

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.dispatch_completed_at < self.dispatch_started_at:
            raise ValueError("dispatch completion cannot predate dispatch start")
        if self.disposition is DemoSubmissionDisposition.ACCEPTED and self.evidence is None:
            raise ValueError("accepted submission requires normalized broker evidence")
        return self


class DemoReconciliationRecord(CoreModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    execution_intent_id: Identifier
    intent_digest: ContentDigest
    status: DemoReconciliationStatus
    reconciled_at: datetime
    evidence: tuple[CompositeBrokerEvidence, ...] = ()
    failure: DemoExecutionFailure | None = None

    _normalize_time = field_validator("reconciled_at")(_utc)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is DemoReconciliationStatus.CONFIRMED:
            if len(self.evidence) != 1 or self.failure is not None:
                raise ValueError("confirmed reconciliation requires exactly one evidence set")
        elif self.failure is None:
            raise ValueError("non-confirmed reconciliation requires a typed failure")
        return self


class DemoExecutionEvent(CoreModel):
    sequence: PositiveInt
    state: DemoExecutionState
    occurred_at: datetime
    failure: DemoExecutionFailure | None = None

    _normalize_time = field_validator("occurred_at")(_utc)


class DemoExecutionRecord(CoreModel):
    """Append-only projection of one intent's durable state transitions."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    intent: DemoOrderIntent
    state: DemoExecutionState
    claim_owner: Identifier | None = None
    preflight: DemoExecutionPreflight | None = None
    risk_revalidation: FreshRiskRevalidation | None = None
    order_check: DemoOrderCheckResult | None = None
    final_guard: FinalDispatchGuardResult | None = None
    submission: DemoSubmissionReceipt | None = None
    reconciliation: DemoReconciliationRecord | None = None
    events: tuple[DemoExecutionEvent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.events[0].state is not DemoExecutionState.CREATED:
            raise ValueError("execution lifecycle must begin at CREATED")
        if self.events[-1].state is not self.state:
            raise ValueError("record state must match its last event")
        if tuple(item.sequence for item in self.events) != tuple(range(1, len(self.events) + 1)):
            raise ValueError("execution event sequence must be contiguous")
        if any(
            right.occurred_at < left.occurred_at
            for left, right in zip(self.events, self.events[1:], strict=False)
        ):
            raise ValueError("execution events must be chronological")
        allowed = {
            DemoExecutionState.CREATED: {DemoExecutionState.CLAIMED},
            DemoExecutionState.CLAIMED: {
                DemoExecutionState.DISPATCHING,
                DemoExecutionState.REJECTED,
            },
            DemoExecutionState.DISPATCHING: {
                DemoExecutionState.SUBMITTED,
                DemoExecutionState.REJECTED,
                DemoExecutionState.UNKNOWN,
            },
            DemoExecutionState.SUBMITTED: {
                DemoExecutionState.CONFIRMED,
                DemoExecutionState.UNKNOWN,
                DemoExecutionState.RECONCILIATION_FAILED,
            },
            DemoExecutionState.UNKNOWN: {
                DemoExecutionState.CONFIRMED,
                DemoExecutionState.RECONCILIATION_FAILED,
            },
        }
        for left, right in zip(self.events, self.events[1:], strict=False):
            if right.state not in allowed.get(left.state, set()):
                raise ValueError("invalid execution state transition")
        if self.state is not DemoExecutionState.CREATED and self.claim_owner is None:
            raise ValueError("claimed execution lifecycle requires its owner")
        if self.state in {
            DemoExecutionState.SUBMITTED,
            DemoExecutionState.CONFIRMED,
            DemoExecutionState.UNKNOWN,
            DemoExecutionState.RECONCILIATION_FAILED,
        } and self.submission is None:
            raise ValueError("post-dispatch state requires a submission receipt")
        if self.state is DemoExecutionState.CONFIRMED and (
            self.reconciliation is None
            or self.reconciliation.status is not DemoReconciliationStatus.CONFIRMED
        ):
            raise ValueError("confirmed state requires confirmed reconciliation")
        return self


class ExecutionControlEvent(CoreModel):
    """Append-only operator/safety transition for the DEMO kill switch."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: Identifier
    previous_state: ExecutionControlState | None
    state: ExecutionControlState
    operator_ref: Identifier
    occurred_at: datetime
    reason: str = Field(min_length=1, max_length=512)

    _normalize_time = field_validator("occurred_at")(_utc)

    @model_validator(mode="after")
    def validate_transition(self) -> Self:
        if self.previous_state is None:
            if self.state is not ExecutionControlState.DISABLED:
                raise ValueError("execution control must initialize as DISABLED")
            return self
        allowed = {
            ExecutionControlState.DISABLED: {
                ExecutionControlState.ENABLED,
                ExecutionControlState.HALTED,
            },
            ExecutionControlState.ENABLED: {
                ExecutionControlState.PAUSED,
                ExecutionControlState.DISABLED,
                ExecutionControlState.HALTED,
            },
            ExecutionControlState.PAUSED: {
                ExecutionControlState.ENABLED,
                ExecutionControlState.DISABLED,
                ExecutionControlState.HALTED,
            },
            ExecutionControlState.HALTED: {ExecutionControlState.DISABLED},
        }
        if self.state not in allowed[self.previous_state]:
            raise ValueError("unsafe execution-control transition")
        return self


def exact_deviation_points(
    maximum_adverse_slippage_ticks: Decimal,
    trade_tick_size: Decimal,
    point: Decimal,
) -> int:
    """Convert tick-bounded slippage to MT5 points without rounding or pip assumptions."""
    if trade_tick_size <= 0 or point <= 0:
        raise ValueError("tick size and point must be positive")
    value = maximum_adverse_slippage_ticks * trade_tick_size / point
    integral = value.to_integral_value()
    if value != integral or integral < 0:
        raise ValueError("slippage ticks must convert to an exact non-negative point count")
    return int(integral)
