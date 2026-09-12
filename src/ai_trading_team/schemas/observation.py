"""Strict M9 continuous SHADOW observation boundary contracts."""

from datetime import UTC, date, datetime
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.common import (
    AccountReference,
    ContentDigest,
    CoreModel,
    CycleId,
    Identifier,
    PositiveDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.enums import (
    AgentRole,
    ContinuousRuntimeState,
    DecisionClaimState,
    M9DecisionDisposition,
    ModelProvider,
    ObservationFailureCategory,
    OutcomeTrackingState,
    RiskBaselineProvenance,
    RiskBaselineState,
    Timeframe,
)
from ai_trading_team.schemas.evaluation import SegmentFacts, TradeOutcome
from ai_trading_team.schemas.replay import OutcomeHorizon
from ai_trading_team.schemas.risk import AccountRiskContext
from ai_trading_team.schemas.shadow import ShadowDecisionRecord, ShadowTradeIntent
from ai_trading_team.schemas.timeframes import timeframe_duration


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)


class CompletedDecisionCandle(CoreModel):
    """One validated completed candle and its stable decision identity."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_key: Identifier
    cycle_id: CycleId
    symbol: Symbol
    timeframe: Literal[Timeframe.M15] = Timeframe.M15
    candle_open_at: datetime
    candle_close_at: datetime
    candle_digest: ContentDigest
    observed_at: datetime

    _normalize_time = field_validator(
        "candle_open_at", "candle_close_at", "observed_at"
    )(_utc)

    @model_validator(mode="after")
    def validate_completed(self) -> Self:
        if self.candle_close_at != self.candle_open_at + timeframe_duration(self.timeframe):
            raise ValueError("decision candle close must use canonical timeframe semantics")
        if self.candle_close_at > self.observed_at:
            raise ValueError("decision candle must be complete when observed")
        return self


class DecisionCandleClaim(CoreModel):
    """Durable binding from candle decision key to cycle and actual snapshot."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_key: Identifier
    cycle_id: CycleId
    actual_snapshot_id: SnapshotId | None = None
    symbol: Symbol
    timeframe: Literal[Timeframe.M15] = Timeframe.M15
    candle_open_at: datetime
    candle_close_at: datetime
    candle_digest: ContentDigest
    state: DecisionClaimState
    discovered_at: datetime
    updated_at: datetime
    failure_category: ObservationFailureCategory | None = None
    sanitized_detail: str | None = Field(default=None, max_length=512)

    _normalize_time = field_validator(
        "candle_open_at", "candle_close_at", "discovered_at", "updated_at"
    )(_utc)

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.updated_at < self.discovered_at:
            raise ValueError("claim update cannot predate discovery")
        if self.candle_close_at != self.candle_open_at + timeframe_duration(self.timeframe):
            raise ValueError("claim candle close is inconsistent")
        terminal_failure = self.state in {
            DecisionClaimState.FAILED,
            DecisionClaimState.MISSED,
            DecisionClaimState.ABANDONED,
        }
        if terminal_failure != (self.failure_category is not None):
            raise ValueError("failure metadata must match a terminal non-completed state")
        if self.failure_category is None and self.sanitized_detail is not None:
            raise ValueError("failure detail requires a failure category")
        if self.state in {
            DecisionClaimState.PROCESSING,
            DecisionClaimState.COMPLETED,
        } and self.actual_snapshot_id is None:
            raise ValueError("processing and completed claims require an accepted snapshot")
        if self.state is DecisionClaimState.DISCOVERED and self.actual_snapshot_id is not None:
            raise ValueError("a discovered claim cannot already bind a snapshot")
        return self


class RiskBaselineRecord(CoreModel):
    """Caller-verified baseline; the runtime never infers cash-flow adjustments."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    baseline_id: Identifier
    account_ref: AccountReference
    utc_trading_day: date
    trading_day_started_at: datetime
    effective_from: datetime
    effective_until: datetime | None = None
    adjusted_day_start_equity: PositiveDecimal
    cash_flow_adjusted_peak_equity: PositiveDecimal
    provenance: RiskBaselineProvenance
    evidence_ref: Identifier
    evidence_digest: ContentDigest
    state: RiskBaselineState
    created_at: datetime
    superseded_by: Identifier | None = None
    invalidation_reason: str | None = Field(default=None, max_length=512)

    _normalize_time = field_validator(
        "trading_day_started_at", "effective_from", "created_at"
    )(_utc)
    _normalize_optional_time = field_validator("effective_until")(_optional_utc)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.trading_day_started_at.date() != self.utc_trading_day:
            raise ValueError("trading-day timestamp must match UTC trading-day identity")
        if self.effective_from < self.trading_day_started_at:
            raise ValueError("baseline cannot be effective before its UTC trading day")
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("baseline effective interval must be increasing")
        if self.state is RiskBaselineState.ACTIVE:
            if self.superseded_by is not None or self.invalidation_reason is not None:
                raise ValueError("active baseline cannot carry terminal lifecycle metadata")
        elif self.state is RiskBaselineState.SUPERSEDED:
            if self.superseded_by is None or self.invalidation_reason is not None:
                raise ValueError("superseded baseline requires its replacement identity")
        elif self.invalidation_reason is None or self.superseded_by is not None:
            raise ValueError("invalidated baseline requires a reason only")
        return self

    def applies_at(self, moment: datetime) -> bool:
        value = _utc(moment)
        return self.effective_from <= value and (
            self.effective_until is None or value < self.effective_until
        )


class AcceptanceEvidenceReference(CoreModel):
    """Exact accepted result dependency used by continuous provider eligibility."""

    acceptance_id: Identifier
    evidence_digest: ContentDigest
    accepted_at: datetime

    _normalize_time = field_validator("accepted_at")(_utc)


class ContinuousProviderAcceptanceRecord(CoreModel):
    """Exact M5 -> M6 -> M9 real-provider acceptance chain."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    acceptance_id: Identifier
    agent_role: AgentRole
    provider: ModelProvider
    model_identifier: Identifier
    adapter_version: SchemaVersion
    provider_sdk_version: str = Field(min_length=1, max_length=128)
    capability_profile_digest: ContentDigest
    runtime_profile_digest: ContentDigest
    prompt_digest: ContentDigest
    input_schema_digest: ContentDigest
    output_schema_digest: ContentDigest
    feature_allowlist_version: SchemaVersion
    feature_allowlist_digest: ContentDigest
    m5_live_smoke: AcceptanceEvidenceReference
    m6_full_shadow: AcceptanceEvidenceReference
    m9_feature_input: AcceptanceEvidenceReference
    accepted_at: datetime
    expires_at: datetime
    accepted: Literal[True] = True

    _normalize_time = field_validator("accepted_at", "expires_at")(_utc)

    @model_validator(mode="after")
    def validate_acceptance(self) -> Self:
        if self.provider is ModelProvider.FAKE:
            raise ValueError("fake providers do not use real-provider acceptance records")
        if self.expires_at <= self.accepted_at:
            raise ValueError("continuous provider acceptance must expire after acceptance")
        evidence = (self.m5_live_smoke, self.m6_full_shadow, self.m9_feature_input)
        if any(item.accepted_at > self.accepted_at for item in evidence):
            raise ValueError("continuous acceptance cannot predate required evidence")
        if len({item.acceptance_id for item in evidence}) != len(evidence):
            raise ValueError("continuous acceptance evidence identities must be distinct")
        return self


class SymbolTimestampAcceptanceRecord(CoreModel):
    """Evidence that exact source timestamp semantics are safe without correction."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    acceptance_id: Identifier
    symbol: Symbol
    timeframes: tuple[Timeframe, ...]
    account_ref: AccountReference
    adapter_version: SchemaVersion
    validation_policy_digest: ContentDigest
    test_result_id: Identifier
    tested_at: datetime
    expires_at: datetime
    accepted: Literal[True] = True

    _normalize_time = field_validator("tested_at", "expires_at")(_utc)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.timeframes != (Timeframe.M15, Timeframe.H1, Timeframe.H4):
            raise ValueError("timestamp acceptance must bind exact M15/H1/H4 semantics")
        if self.expires_at <= self.tested_at:
            raise ValueError("timestamp acceptance must have a finite future expiry")
        return self


class RiskContextEvidence(CoreModel):
    baseline_id: Identifier
    baseline_digest: ContentDigest
    account_observation_digest: ContentDigest
    positions_observation_digest: ContentDigest
    context: AccountRiskContext


class ContinuousDecisionRecord(CoreModel):
    """Sanitized result joining M9 discovery with an optional exact M6 record."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    record_id: Identifier
    decision_key: Identifier
    cycle_id: CycleId
    actual_snapshot_id: SnapshotId | None = None
    symbol: Symbol
    timeframe: Literal[Timeframe.M15] = Timeframe.M15
    decision_candle_digest: ContentDigest
    disposition: M9DecisionDisposition
    recorded_at: datetime
    snapshot_digest: ContentDigest | None = None
    feature_set_digest: ContentDigest | None = None
    agent_feature_view_digest: ContentDigest | None = None
    agent_market_view: AgentMarketView | None = None
    risk_context_evidence: RiskContextEvidence | None = None
    shadow_record: ShadowDecisionRecord | None = None
    failure_category: ObservationFailureCategory | None = None
    sanitized_detail: str | None = Field(default=None, max_length=512)

    _normalize_time = field_validator("recorded_at")(_utc)

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.actual_snapshot_id is None and any(
            item is not None
            for item in (
                self.snapshot_digest,
                self.feature_set_digest,
                self.agent_feature_view_digest,
                self.agent_market_view,
                self.risk_context_evidence,
                self.shadow_record,
            )
        ):
            raise ValueError("snapshot-owned artifacts require an accepted snapshot identity")
        if self.agent_market_view is not None:
            if self.agent_market_view.schema_version != "2.0.0":
                raise ValueError("M9 records require AgentMarketView v2")
            if self.agent_feature_view_digest != self.agent_market_view.agent_feature_view_digest:
                raise ValueError("recorded feature-view digest must match the exact agent view")
            if (
                self.agent_market_view.cycle_id != self.cycle_id
                or self.agent_market_view.snapshot_id != self.actual_snapshot_id
                or self.agent_market_view.symbol != self.symbol
            ):
                raise ValueError("recorded agent view must match the M9 decision binding")
        if self.risk_context_evidence is not None:
            context = self.risk_context_evidence.context
            if (
                context.cycle_id != self.cycle_id
                or context.snapshot_id != self.actual_snapshot_id
            ):
                raise ValueError("risk context evidence must match the M9 decision binding")
        if self.shadow_record is not None:
            cycle = self.shadow_record.decision_cycle
            if (
                cycle.cycle_id != self.cycle_id
                or cycle.initial_snapshot_id != self.actual_snapshot_id
                or cycle.symbol != self.symbol
            ):
                raise ValueError("shadow record must match M9 decision binding")
        if self.disposition is M9DecisionDisposition.SHADOW_RECORDED:
            if (
                self.shadow_record is None
                or self.failure_category is not None
                or self.actual_snapshot_id is None
                or self.snapshot_digest is None
                or self.feature_set_digest is None
                or self.agent_market_view is None
                or self.risk_context_evidence is None
            ):
                raise ValueError("recorded SHADOW disposition requires an M6 record only")
        elif self.failure_category is None or self.shadow_record is not None:
            raise ValueError("non-shadow M9 result requires a failure and no M6 record")
        return self


class PendingShadowOutcome(CoreModel):
    """Immutable-decision tracking state owned outside the decision runtime."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    tracking_id: Identifier
    decision_record_id: Identifier
    decision_record_digest: ContentDigest
    shadow_intent: ShadowTradeIntent
    decision_candle_close_at: datetime
    horizon: OutcomeHorizon
    segment_facts: SegmentFacts
    state: OutcomeTrackingState = OutcomeTrackingState.PENDING
    created_at: datetime
    updated_at: datetime
    outcome: TradeOutcome | None = None
    failure_category: ObservationFailureCategory | None = None

    _normalize_time = field_validator(
        "decision_candle_close_at", "created_at", "updated_at"
    )(_utc)

    @model_validator(mode="after")
    def validate_tracking(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("outcome tracking update cannot predate creation")
        if self.state is OutcomeTrackingState.PENDING and (
            self.outcome is not None or self.failure_category is not None
        ):
            raise ValueError("pending outcome cannot contain a terminal result")
        if self.state is OutcomeTrackingState.FAILED:
            if self.failure_category is None or self.outcome is not None:
                raise ValueError("failed tracking requires a failure without an outcome")
        elif self.state is not OutcomeTrackingState.PENDING and self.outcome is None:
            raise ValueError("terminal outcome tracking requires a TradeOutcome")
        return self


class ContinuousRuntimeHealth(CoreModel):
    """Safe operational telemetry without credentials or raw account identity."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    state: ContinuousRuntimeState
    symbol: Symbol
    timeframe: Literal[Timeframe.M15] = Timeframe.M15
    started_at: datetime | None = None
    last_poll_at: datetime | None = None
    last_observed_candle_close_at: datetime | None = None
    last_completed_cycle_id: CycleId | None = None
    in_flight_count: NonNegativeInt = 0
    pending_count: NonNegativeInt = 0
    missed_count: NonNegativeInt = 0
    pending_outcome_count: NonNegativeInt = 0
    symbol_eligible: bool = False
    providers_eligible: bool = False
    budget_available: bool | None = None
    last_failure_category: ObservationFailureCategory | None = None
    updated_at: datetime

    _normalize_optional_times = field_validator(
        "started_at", "last_poll_at", "last_observed_candle_close_at"
    )(_optional_utc)
    _normalize_updated = field_validator("updated_at")(_utc)
