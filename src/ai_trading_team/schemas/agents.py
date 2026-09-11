"""Strict M4 agent metadata, sanitized market views, and role outputs."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, field_validator, model_validator

from ai_trading_team.schemas.common import (
    AgentName,
    Confidence,
    ContentDigest,
    CoreModel,
    CycleId,
    FiniteDecimal,
    Identifier,
    NonNegativeDecimal,
    SchemaVersion,
    SnapshotId,
    Symbol,
)
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    AgentExecutionProfile,
    AgentInvocationMode,
    AgentOutputStatus,
    AgentRole,
    DirectionalBias,
    EntryDisposition,
    EvidenceKind,
    MarketRegime,
    QuantEvidenceStatus,
    QuantReviewStatus,
    SkepticVerdict,
    SnapshotWarningCode,
    SymbolTradeMode,
    Timeframe,
    TradeAction,
    TradeSide,
    TrendStrength,
)
from ai_trading_team.schemas.market import MarketSnapshot, SnapshotFreshness


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class PromptReference(CoreModel):
    """Version metadata only; M4 stores and transmits no prompt content."""

    prompt_id: Identifier
    prompt_version: SchemaVersion
    content_digest: ContentDigest | None = None


class AgentDescriptor(CoreModel):
    """Immutable role and vendor-neutral future runtime assignment metadata."""

    agent_name: AgentName
    role: AgentRole
    agent_version: SchemaVersion
    prompt_ref: PromptReference
    execution_profile: AgentExecutionProfile
    runtime_profile_ref: Identifier
    invocation_mode: AgentInvocationMode
    invocation_policy_ref: Identifier
    cost_policy_ref: Identifier | None = None

    @model_validator(mode="after")
    def validate_profile_and_invocation_mode(self) -> Self:
        allowed_modes = {
            AgentExecutionProfile.REALTIME: {AgentInvocationMode.REALTIME},
            AgentExecutionProfile.CONDITIONAL: {AgentInvocationMode.CANDIDATE_ONLY},
            AgentExecutionProfile.OFFLINE: {
                AgentInvocationMode.PERIODIC,
                AgentInvocationMode.OFFLINE,
            },
        }
        if self.invocation_mode not in allowed_modes[self.execution_profile]:
            raise ValueError("invocation mode is incompatible with execution profile")
        return self


class AgentCandle(CoreModel):
    """Completed candle safe for an AI-facing context."""

    symbol: Symbol
    timeframe: Timeframe
    open_time: datetime
    open: FiniteDecimal
    high: FiniteDecimal
    low: FiniteDecimal
    close: FiniteDecimal
    tick_volume: NonNegativeInt
    real_volume: NonNegativeInt

    _normalize_time = field_validator("open_time")(_utc)

    @model_validator(mode="after")
    def validate_ohlc(self) -> Self:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("candle high/low must contain open and close")
        if self.high < self.low:
            raise ValueError("candle high must not be below candle low")
        return self


class AgentCandleSet(CoreModel):
    """Sanitized completed multi-timeframe histories."""

    m15: tuple[AgentCandle, ...] = Field(min_length=1)
    h1: tuple[AgentCandle, ...] = Field(min_length=1)
    h4: tuple[AgentCandle, ...] = Field(min_length=1)


class AgentTickView(CoreModel):
    """Market-only tick fields; no terminal object or account metadata."""

    symbol: Symbol
    source_time: datetime
    bid: FiniteDecimal
    ask: FiniteDecimal
    spread: NonNegativeDecimal
    last: FiniteDecimal
    volume: NonNegativeDecimal

    _normalize_time = field_validator("source_time")(_utc)

    @model_validator(mode="after")
    def validate_spread(self) -> Self:
        if self.ask < self.bid or self.spread != self.ask - self.bid:
            raise ValueError("tick spread must equal ask minus bid")
        return self


class AgentSymbolView(CoreModel):
    """Analysis-safe broker metadata with all position-sizing fields omitted."""

    symbol: Symbol
    digits: NonNegativeInt
    point: NonNegativeDecimal
    trade_tick_size: NonNegativeDecimal
    trade_stops_level: NonNegativeInt
    trading_mode: SymbolTradeMode


class AgentMarketView(CoreModel):
    """Least-privilege, immutable projection of one valid M2 snapshot."""

    schema_version: SchemaVersion = "1.0.0"
    source_schema_version: SchemaVersion
    cycle_id: CycleId
    snapshot_id: SnapshotId
    symbol: Symbol
    primary_timeframe: Timeframe
    snapshot_completed_at: datetime
    symbol_info: AgentSymbolView
    tick: AgentTickView
    candles: AgentCandleSet
    freshness: SnapshotFreshness
    validation_warning_codes: tuple[SnapshotWarningCode, ...] = ()
    symbol_open_position_count: NonNegativeInt

    _normalize_time = field_validator("snapshot_completed_at")(_utc)

    @classmethod
    def from_snapshot(cls, snapshot: MarketSnapshot) -> "AgentMarketView":
        """Create a safe projection without account identity or position details."""
        return cls(
            source_schema_version=snapshot.schema_version,
            cycle_id=snapshot.cycle_id,
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            primary_timeframe=snapshot.primary_timeframe,
            snapshot_completed_at=snapshot.snapshot_completed_at,
            symbol_info=AgentSymbolView(
                symbol=snapshot.symbol_info.symbol,
                digits=snapshot.symbol_info.digits,
                point=snapshot.symbol_info.point,
                trade_tick_size=snapshot.symbol_info.trade_tick_size,
                trade_stops_level=snapshot.symbol_info.trade_stops_level,
                trading_mode=snapshot.symbol_info.trading_mode,
            ),
            tick=AgentTickView(
                symbol=snapshot.tick.symbol,
                source_time=snapshot.tick.source_time,
                bid=snapshot.tick.bid,
                ask=snapshot.tick.ask,
                spread=snapshot.spread,
                last=snapshot.tick.last,
                volume=snapshot.tick.volume,
            ),
            candles=AgentCandleSet(
                m15=tuple(cls._candle_view(item) for item in snapshot.candles.m15),
                h1=tuple(cls._candle_view(item) for item in snapshot.candles.h1),
                h4=tuple(cls._candle_view(item) for item in snapshot.candles.h4),
            ),
            freshness=snapshot.consistency.freshness,
            validation_warning_codes=tuple(
                warning.code for warning in snapshot.consistency.validation_warnings
            ),
            symbol_open_position_count=len(snapshot.open_positions),
        )

    @staticmethod
    def _candle_view(candle: object) -> AgentCandle:
        from ai_trading_team.schemas.mt5 import MT5Candle

        if not isinstance(candle, MT5Candle):
            raise TypeError("snapshot candle has an unexpected boundary type")
        return AgentCandle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            open_time=candle.open_time,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            tick_volume=candle.tick_volume,
            real_volume=candle.real_volume,
        )

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.symbol_info.symbol != self.symbol or self.tick.symbol != self.symbol:
            raise ValueError("market-view observations must match its symbol")
        collections = (
            (Timeframe.M15, self.candles.m15),
            (Timeframe.H1, self.candles.h1),
            (Timeframe.H4, self.candles.h4),
        )
        if any(
            candle.symbol != self.symbol or candle.timeframe is not timeframe
            for timeframe, candles in collections
            for candle in candles
        ):
            raise ValueError("market-view candles must match symbol and timeframe")
        return self


class AgentEvidence(CoreModel):
    """One attributable claim, explicitly classified by evidence kind."""

    evidence_id: Identifier
    kind: EvidenceKind
    summary: str = Field(min_length=1, max_length=1_024)
    source_refs: tuple[Identifier, ...] = ()


class AgentWarning(CoreModel):
    """Typed warning retained with an otherwise valid agent output."""

    code: Identifier
    message: str = Field(min_length=1, max_length=512)


class AgentInvalidation(CoreModel):
    """Condition that would invalidate an analysis conclusion."""

    condition: str = Field(min_length=1, max_length=1_024)
    source_refs: tuple[Identifier, ...] = ()


class AgentOutput[PayloadT: CoreModel](CoreModel):
    """Common immutable envelope for one structurally valid role output."""

    schema_version: SchemaVersion = "1.0.0"
    output_id: Identifier
    cycle_id: CycleId
    snapshot_id: SnapshotId
    agent_name: AgentName
    agent_role: AgentRole
    agent_version: SchemaVersion
    prompt_ref: PromptReference
    runtime_profile_ref: Identifier
    invocation_policy_ref: Identifier
    cost_policy_ref: Identifier | None = None
    produced_at: datetime
    status: AgentOutputStatus
    confidence: Confidence
    evidence: tuple[AgentEvidence, ...] = ()
    warnings: tuple[AgentWarning, ...] = ()
    invalidations: tuple[AgentInvalidation, ...] = ()
    payload: PayloadT

    _normalize_time = field_validator("produced_at")(_utc)

    @model_validator(mode="after")
    def validate_degraded_output(self) -> Self:
        if self.status is AgentOutputStatus.DEGRADED and not self.warnings:
            raise ValueError("degraded output requires at least one warning")
        return self


class MarketContextResult(CoreModel):
    regime: MarketRegime
    summary: str = Field(min_length=1, max_length=2_048)


class TrendAnalysisResult(CoreModel):
    bias: DirectionalBias
    strength: TrendStrength
    summary: str = Field(min_length=1, max_length=2_048)


class PriceActionResult(CoreModel):
    bias: DirectionalBias
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]


class EntryAnalysisResult(CoreModel):
    disposition: EntryDisposition
    side: TradeSide | None = None
    entry: FiniteDecimal | None = None
    stop_loss: FiniteDecimal | None = None
    take_profit: FiniteDecimal | None = None
    rationale: str = Field(min_length=1, max_length=2_048)

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        prices = (self.entry, self.stop_loss, self.take_profit)
        if self.disposition is EntryDisposition.NO_ENTRY:
            if self.side is not None or any(price is not None for price in prices):
                raise ValueError("NO_ENTRY must not carry a directional price candidate")
        elif self.disposition is EntryDisposition.ENTER_NOW and (
            self.side is None or self.entry is None or self.stop_loss is None
        ):
            raise ValueError("ENTER_NOW requires side, entry, and stop loss")
        return self


class QuantResearchResult(CoreModel):
    hypothesis: str = Field(min_length=1, max_length=2_048)
    status: QuantEvidenceStatus
    evidence_refs: tuple[Identifier, ...] = ()
    limitations: tuple[str, ...] = ()


class QuantDeveloperReview(CoreModel):
    status: QuantReviewStatus
    data_integrity_findings: tuple[str, ...] = ()
    leakage_risks: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()


class SkepticReview(CoreModel):
    verdict: SkepticVerdict
    challenged_output_ids: tuple[Identifier, ...] = ()
    objections: tuple[str, ...] = ()


class ChiefTraderResult(CoreModel):
    action: TradeAction
    rationale: str = Field(min_length=1, max_length=2_048)
    trade_proposal: TradeProposal | None = None

    @model_validator(mode="after")
    def validate_action_and_proposal(self) -> Self:
        if self.action is TradeAction.HOLD and self.trade_proposal is not None:
            raise ValueError("HOLD must not include a trade proposal")
        if self.action in (TradeAction.BUY, TradeAction.SELL):
            if self.trade_proposal is None:
                raise ValueError("BUY or SELL requires a trade proposal")
            if self.trade_proposal.side.value != self.action.value:
                raise ValueError("trade proposal side must match Chief action")
        return self


class PerformanceReviewResult(CoreModel):
    findings: tuple[str, ...]
    recommendations: tuple[str, ...]
    automatic_strategy_change_permitted: Literal[False] = False


class MarketContextOutput(AgentOutput[MarketContextResult]):
    agent_role: Literal[AgentRole.MARKET_CONTEXT]


class TrendAnalysisOutput(AgentOutput[TrendAnalysisResult]):
    agent_role: Literal[AgentRole.TREND_ANALYST]


class PriceActionOutput(AgentOutput[PriceActionResult]):
    agent_role: Literal[AgentRole.PRICE_ACTION_ANALYST]


class EntryAnalysisOutput(AgentOutput[EntryAnalysisResult]):
    agent_role: Literal[AgentRole.ENTRY_ANALYST]


class QuantResearchOutput(AgentOutput[QuantResearchResult]):
    agent_role: Literal[AgentRole.QUANT_RESEARCHER]


class QuantDeveloperOutput(AgentOutput[QuantDeveloperReview]):
    agent_role: Literal[AgentRole.SENIOR_QUANT_DEVELOPER]


class SkepticOutput(AgentOutput[SkepticReview]):
    agent_role: Literal[AgentRole.SKEPTIC]


class ChiefTraderOutput(AgentOutput[ChiefTraderResult]):
    agent_role: Literal[AgentRole.CHIEF_TRADER]

    @model_validator(mode="after")
    def validate_proposal_trace(self) -> Self:
        proposal = self.payload.trade_proposal
        if proposal is not None and (
            proposal.cycle_id != self.cycle_id or proposal.snapshot_id != self.snapshot_id
        ):
            raise ValueError("Chief proposal must match output cycle and snapshot")
        return self


class PerformanceReviewOutput(AgentOutput[PerformanceReviewResult]):
    agent_role: Literal[AgentRole.PERFORMANCE_REVIEWER]
