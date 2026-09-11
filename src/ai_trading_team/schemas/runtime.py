"""Strict provider-neutral M5 runtime, telemetry, and budget contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    Field,
    NonNegativeInt,
    PositiveInt,
    SerializeAsAny,
    field_validator,
    model_validator,
)

from ai_trading_team.schemas.agents import (
    AgentDescriptor,
    AgentEvidence,
    AgentInvalidation,
    AgentWarning,
)
from ai_trading_team.schemas.common import (
    Confidence,
    ContentDigest,
    CoreModel,
    CycleId,
    Identifier,
    NonNegativeDecimal,
    SchemaVersion,
    SnapshotId,
)
from ai_trading_team.schemas.enums import (
    AgentRole,
    BudgetReservationState,
    MetricAvailability,
    ModelProvider,
    ReasoningEffort,
    RuntimeFailureCategory,
    TokenEstimateMethod,
    UsageMetric,
)
from ai_trading_team.schemas.orchestration import AgentFailureRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class SchemaReference(CoreModel):
    """Stable identity and digest for one boundary schema."""

    schema_id: Identifier
    schema_version: SchemaVersion
    schema_digest: ContentDigest


class PromptArtifact(CoreModel):
    """Immutable trusted prompt content loaded from the prompt registry."""

    prompt_id: Identifier
    prompt_version: SchemaVersion
    role: AgentRole
    content: str = Field(min_length=1, max_length=32_768)
    content_digest: ContentDigest
    compatible_input_schema: SchemaReference
    compatible_output_schema: SchemaReference


class RuntimeProfile(CoreModel):
    """Requested provider/model behavior, separate from proven capabilities."""

    profile_ref: Identifier
    profile_version: SchemaVersion
    provider: ModelProvider
    model_identifier: Identifier
    request_timeout_seconds: PositiveInt = 30
    total_timeout_seconds: PositiveInt = 90
    max_output_tokens: PositiveInt = 1_024
    reasoning_effort: ReasoningEffort = ReasoningEffort.NONE
    require_structured_output: Literal[True] = True
    require_json_schema: Literal[True] = True
    capability_profile_ref: Identifier
    retry_policy_ref: Identifier
    cost_policy_ref: Identifier
    pricing_profile_ref: Identifier

    @model_validator(mode="after")
    def validate_timeout_budget(self) -> Self:
        if self.total_timeout_seconds < self.request_timeout_seconds:
            raise ValueError("total timeout must be at least one request timeout")
        return self


class RetryPolicy(CoreModel):
    """Bounded retry eligibility; max_attempts includes the initial provider call."""

    policy_ref: Identifier
    policy_version: SchemaVersion
    max_attempts: int = Field(default=3, ge=1, le=3)
    retry_timeouts: bool = True
    retry_transient_errors: bool = True
    retry_rate_limits: bool = False


class ModelCapabilityProfile(CoreModel):
    """Validated capabilities for one exact provider/model pairing."""

    profile_ref: Identifier
    profile_version: SchemaVersion
    provider: ModelProvider
    model_identifier: Identifier
    structured_output_supported: bool
    json_schema_supported: bool
    reasoning_configuration_supported: bool
    supported_reasoning_efforts: tuple[ReasoningEffort, ...]
    max_context_tokens: PositiveInt
    max_output_tokens: PositiveInt
    usage_metrics: frozenset[UsageMetric] = frozenset()
    token_estimation_methods: frozenset[TokenEstimateMethod] = frozenset()
    adapter_contract_accepted: bool = False
    live_smoke_accepted: bool = False

    @model_validator(mode="after")
    def validate_capabilities(self) -> Self:
        if ReasoningEffort.NONE not in self.supported_reasoning_efforts:
            raise ValueError("NONE must be a supported reasoning effort")
        if self.reasoning_configuration_supported is False and self.supported_reasoning_efforts != (
            ReasoningEffort.NONE,
        ):
            raise ValueError("unsupported reasoning configuration may only declare NONE")
        return self


class TokenEstimate(CoreModel):
    """Token quantity with explicit estimation provenance."""

    tokens: NonNegativeInt | None
    method: TokenEstimateMethod
    conservative: bool
    estimated_at: datetime

    _normalize_time = field_validator("estimated_at")(_utc)

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if self.method is TokenEstimateMethod.UNAVAILABLE:
            if self.tokens is not None or self.conservative:
                raise ValueError("unavailable estimates must not carry a value")
        elif self.tokens is None:
            raise ValueError("available token estimates require a value")
        return self


class UsageValue(CoreModel):
    """One usage measurement with explicit availability."""

    value: NonNegativeInt | None
    availability: MetricAvailability

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if self.availability is MetricAvailability.UNAVAILABLE and self.value is not None:
            raise ValueError("unavailable metric must not carry a value")
        if self.availability is not MetricAvailability.UNAVAILABLE and self.value is None:
            raise ValueError("available metric requires a value")
        return self


def unavailable_usage() -> UsageValue:
    return UsageValue(value=None, availability=MetricAvailability.UNAVAILABLE)


class InvocationUsage(CoreModel):
    """Normalized provider usage; missing fields stay explicitly unavailable."""

    input_tokens: UsageValue = Field(default_factory=unavailable_usage)
    cached_input_tokens: UsageValue = Field(default_factory=unavailable_usage)
    output_tokens: UsageValue = Field(default_factory=unavailable_usage)
    reasoning_tokens: UsageValue = Field(default_factory=unavailable_usage)


class PricingProfile(CoreModel):
    """Caller-owned versioned pricing; M5 embeds no vendor prices."""

    profile_ref: Identifier
    profile_version: SchemaVersion
    provider: ModelProvider
    model_identifier: Identifier
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    input_cost_per_million_tokens: NonNegativeDecimal
    output_cost_per_million_tokens: NonNegativeDecimal
    valid_from: datetime
    valid_until: datetime | None = None

    _normalize_from = field_validator("valid_from")(_utc)
    _normalize_until = field_validator("valid_until")(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("pricing validity window must be increasing")
        return self


class AIBudgetPolicy(CoreModel):
    """Deterministic call, token, and monetary limits."""

    policy_ref: Identifier
    policy_version: SchemaVersion
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    maximum_estimated_cost_per_call: NonNegativeDecimal
    daily_budget: NonNegativeDecimal
    monthly_budget: NonNegativeDecimal
    maximum_calls_per_cycle: PositiveInt
    maximum_calls_per_day: PositiveInt
    maximum_input_tokens: PositiveInt
    maximum_output_tokens: PositiveInt


class BudgetReservation(CoreModel):
    """Auditable conservative reservation for one unique invocation."""

    invocation_id: Identifier
    cycle_id: CycleId
    policy_ref: Identifier
    state: BudgetReservationState
    reserved_amount: NonNegativeDecimal
    settled_amount: NonNegativeDecimal | None = None
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    created_at: datetime
    updated_at: datetime

    _normalize_created = field_validator("created_at")(_utc)
    _normalize_updated = field_validator("updated_at")(_utc)


class AgentInvocationRequest(CoreModel):
    """One caller-owned, traceable, single-agent invocation request."""

    schema_version: SchemaVersion = "1.0.0"
    invocation_id: Identifier
    output_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    descriptor: AgentDescriptor
    requested_at: datetime
    input_schema: SchemaReference
    output_schema: SchemaReference
    context: SerializeAsAny[CoreModel]

    _normalize_time = field_validator("requested_at")(_utc)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        context_cycle = getattr(self.context, "cycle_id", None)
        context_snapshot = getattr(self.context, "snapshot_id", None)
        if context_cycle != self.cycle_id or context_snapshot != self.snapshot_id:
            raise ValueError("context trace identifiers must match invocation request")
        return self


class ModelGeneratedAgentBody[PayloadT: CoreModel](CoreModel):
    """Untrusted semantic model body; runtime status is intentionally absent."""

    confidence: Confidence
    evidence: tuple[AgentEvidence, ...] = ()
    warnings: tuple[AgentWarning, ...] = ()
    invalidations: tuple[AgentInvalidation, ...] = ()
    payload: PayloadT


class ProviderRequest(CoreModel):
    """Sanitized provider dispatch payload; credentials are resolved by adapters."""

    invocation_id: Identifier
    provider: ModelProvider
    model_identifier: Identifier
    attempt: int = Field(ge=1, le=3)
    system_prompt: str = Field(min_length=1, max_length=32_768)
    context_json: str = Field(min_length=2)
    output_json_schema: str = Field(min_length=2)
    max_output_tokens: PositiveInt
    timeout_seconds: PositiveInt
    reasoning_effort: ReasoningEffort


class ProviderResponse(CoreModel):
    """Provider-neutral response after raw SDK objects have been normalized."""

    response_json: str
    provider_request_id: Identifier | None = None
    model_identifier: Identifier
    responded_at: datetime
    usage: InvocationUsage = Field(default_factory=InvocationUsage)

    _normalize_time = field_validator("responded_at")(_utc)


class InvocationTrace(CoreModel):
    """Trusted metadata spanning request, provider dispatch, and result."""

    invocation_id: Identifier
    output_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    agent_role: AgentRole
    agent_version: SchemaVersion
    prompt_id: Identifier
    prompt_version: SchemaVersion
    prompt_digest: ContentDigest
    runtime_profile_ref: Identifier
    provider: ModelProvider
    model_identifier: Identifier
    request_started_at: datetime
    request_completed_at: datetime
    attempts: NonNegativeInt

    _normalize_started = field_validator("request_started_at")(_utc)
    _normalize_completed = field_validator("request_completed_at")(_utc)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.request_completed_at < self.request_started_at:
            raise ValueError("invocation timestamps must be increasing")
        return self


class InvocationTelemetry(CoreModel):
    """Normalized per-invocation usage, latency, and cost."""

    usage: InvocationUsage
    input_estimate: TokenEstimate
    attempt_count: NonNegativeInt
    retry_count: NonNegativeInt
    latency_milliseconds: NonNegativeDecimal
    estimated_cost: Decimal | None
    estimated_cost_availability: MetricAvailability
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    provider_request_id: Identifier | None = None
    reservation_state: BudgetReservationState | None

    @model_validator(mode="after")
    def validate_cost(self) -> Self:
        if self.retry_count != max(self.attempt_count - 1, 0):
            raise ValueError("retry count must be derived from total attempts")
        if self.estimated_cost_availability is MetricAvailability.UNAVAILABLE:
            if self.estimated_cost is not None:
                raise ValueError("unavailable cost must not carry a value")
        elif self.estimated_cost is None or self.estimated_cost < 0:
            raise ValueError("available estimated cost must be non-negative")
        return self


class AgentInvocationResult(CoreModel):
    """Exactly one trusted typed output or sanitized failure."""

    trace: InvocationTrace
    output: SerializeAsAny[CoreModel] | None = None
    failure: AgentFailureRecord | None = None
    runtime_failure_category: RuntimeFailureCategory | None = None
    telemetry: InvocationTelemetry

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if (self.output is None) == (self.failure is None):
            raise ValueError("result requires exactly one of output or failure")
        if self.failure is None and self.runtime_failure_category is not None:
            raise ValueError("successful result must not include a failure category")
        if self.failure is not None and self.runtime_failure_category is None:
            raise ValueError("failed result requires a runtime failure category")
        return self
