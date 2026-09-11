"""Finite domain states kept separate by responsibility."""

from enum import IntEnum, StrEnum


class ApplicationMode(StrEnum):
    """How the application is intended to operate."""

    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    DEMO = "DEMO"
    LIVE = "LIVE"


class RiskState(StrEnum):
    """Account-level risk posture, independent of application mode."""

    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    SAFE_MODE = "SAFE_MODE"
    HALTED = "HALTED"


class RiskDecisionStatus(StrEnum):
    """Outcome produced by the deterministic Risk Engine."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HALTED = "HALTED"


class PositionSizingStatus(StrEnum):
    """Outcome of deterministic broker-volume sizing."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RiskReasonCode(StrEnum):
    """Stable machine-readable explanations for M3 risk decisions."""

    TRACEABILITY_MISMATCH = "TRACEABILITY_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    ACCOUNT_CONTEXT_MISMATCH = "ACCOUNT_CONTEXT_MISMATCH"
    ACCOUNT_CONTEXT_FUTURE_DATED = "ACCOUNT_CONTEXT_FUTURE_DATED"
    ACCOUNT_CONTEXT_PREDATES_SNAPSHOT = "ACCOUNT_CONTEXT_PREDATES_SNAPSHOT"
    TRADING_DAY_CONTEXT_INVALID = "TRADING_DAY_CONTEXT_INVALID"
    EVALUATION_TIMESTAMP_INVALID = "EVALUATION_TIMESTAMP_INVALID"
    ENTRY_PRICE_REQUIRED = "ENTRY_PRICE_REQUIRED"
    ENTRY_PRICE_INVALID = "ENTRY_PRICE_INVALID"
    STOP_LOSS_REQUIRED = "STOP_LOSS_REQUIRED"
    STOP_LOSS_INVALID = "STOP_LOSS_INVALID"
    TAKE_PROFIT_REQUIRED = "TAKE_PROFIT_REQUIRED"
    TAKE_PROFIT_INVALID = "TAKE_PROFIT_INVALID"
    INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
    INVALID_TAKE_PROFIT_GEOMETRY = "INVALID_TAKE_PROFIT_GEOMETRY"
    PRICE_NOT_ALIGNED_TO_TICK_SIZE = "PRICE_NOT_ALIGNED_TO_TICK_SIZE"
    STOP_DISTANCE_BELOW_BROKER_MINIMUM = "STOP_DISTANCE_BELOW_BROKER_MINIMUM"
    TAKE_PROFIT_DISTANCE_BELOW_BROKER_MINIMUM = (
        "TAKE_PROFIT_DISTANCE_BELOW_BROKER_MINIMUM"
    )
    RISK_REWARD_BELOW_MINIMUM = "RISK_REWARD_BELOW_MINIMUM"
    SYMBOL_TRADING_DISABLED = "SYMBOL_TRADING_DISABLED"
    TRADE_SIDE_NOT_ALLOWED = "TRADE_SIDE_NOT_ALLOWED"
    ACCOUNT_TRADING_DISABLED = "ACCOUNT_TRADING_DISABLED"
    EXPERT_TRADING_DISABLED = "EXPERT_TRADING_DISABLED"
    NON_POSITIVE_EQUITY = "NON_POSITIVE_EQUITY"
    ACCOUNT_POSITION_COUNT_INCONSISTENT = "ACCOUNT_POSITION_COUNT_INCONSISTENT"
    MAXIMUM_POSITIONS_REACHED = "MAXIMUM_POSITIONS_REACHED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    MAXIMUM_DRAWDOWN_REACHED = "MAXIMUM_DRAWDOWN_REACHED"
    INVALID_BROKER_RISK_METADATA = "INVALID_BROKER_RISK_METADATA"
    MINIMUM_VOLUME_EXCEEDS_RISK = "MINIMUM_VOLUME_EXCEEDS_RISK"
    POSITION_SIZE_INVARIANT_FAILED = "POSITION_SIZE_INVARIANT_FAILED"


class TradeAction(StrEnum):
    """Permitted high-level decision actions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSide(StrEnum):
    """Directional side for a proposal; HOLD is intentionally excluded."""

    BUY = "BUY"
    SELL = "SELL"


class Timeframe(StrEnum):
    """Initial configured analysis timeframes."""

    M15 = "M15"
    H1 = "H1"
    H4 = "H4"


class DataValidityState(StrEnum):
    """Structural validity, kept independent from freshness and tradeability."""

    VALID = "VALID"
    INVALID = "INVALID"


class FreshnessState(StrEnum):
    """Whether a structurally valid observation is within its configured age limit."""

    FRESH = "FRESH"
    STALE = "STALE"


class SnapshotWarningCode(StrEnum):
    """Non-fatal consistency and freshness findings attached to a valid snapshot."""

    STALE_TICK = "STALE_TICK"
    STALE_ACCOUNT = "STALE_ACCOUNT"
    STALE_CANDLE = "STALE_CANDLE"
    SLOW_SNAPSHOT = "SLOW_SNAPSHOT"
    OUT_OF_SCOPE_POSITION_OMITTED = "OUT_OF_SCOPE_POSITION_OMITTED"


class MarketRegime(StrEnum):
    """Finite market-context labels specified for future analysis."""

    TREND = "TREND"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"
    UNCERTAIN = "UNCERTAIN"


class MT5ConnectionState(StrEnum):
    """Observed MT5 terminal connection state."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class BrokerAccountMode(IntEnum):
    """MetaTrader 5 broker account classification."""

    DEMO = 0
    CONTEST = 1
    REAL = 2


class SymbolTradeMode(IntEnum):
    """MetaTrader 5 symbol trading availability value."""

    DISABLED = 0
    LONG_ONLY = 1
    SHORT_ONLY = 2
    CLOSE_ONLY = 3
    FULL = 4


class BrokerPositionSide(IntEnum):
    """Direction reported for an existing broker position."""

    BUY = 0
    SELL = 1


class AgentRole(StrEnum):
    """Stable identities for the nine specified AI roles."""

    MARKET_CONTEXT = "MARKET_CONTEXT"
    TREND_ANALYST = "TREND_ANALYST"
    PRICE_ACTION_ANALYST = "PRICE_ACTION_ANALYST"
    ENTRY_ANALYST = "ENTRY_ANALYST"
    QUANT_RESEARCHER = "QUANT_RESEARCHER"
    SENIOR_QUANT_DEVELOPER = "SENIOR_QUANT_DEVELOPER"
    SKEPTIC = "SKEPTIC"
    CHIEF_TRADER = "CHIEF_TRADER"
    PERFORMANCE_REVIEWER = "PERFORMANCE_REVIEWER"


class AgentExecutionProfile(StrEnum):
    """Where a configured role is eligible to be invoked in a future runtime."""

    REALTIME = "REALTIME"
    CONDITIONAL = "CONDITIONAL"
    OFFLINE = "OFFLINE"


class AgentInvocationMode(StrEnum):
    """Inert invocation-policy classification; M4 performs no scheduling."""

    REALTIME = "REALTIME"
    CANDIDATE_ONLY = "CANDIDATE_ONLY"
    PERIODIC = "PERIODIC"
    OFFLINE = "OFFLINE"


class AgentOutputStatus(StrEnum):
    """Status of a structurally valid agent output."""

    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"


class AgentFailureCategory(StrEnum):
    """Failures handled by deterministic orchestration policy."""

    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    MISSING_REQUIRED_UPSTREAM = "MISSING_REQUIRED_UPSTREAM"
    UNAVAILABLE_AGENT = "UNAVAILABLE_AGENT"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"
    INVALID_SNAPSHOT = "INVALID_SNAPSHOT"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    UNKNOWN = "UNKNOWN"


class FailureDisposition(StrEnum):
    """Safe action selected for an agent or input failure."""

    CONTINUE_DEGRADED = "CONTINUE_DEGRADED"
    HOLD = "HOLD"
    ABORT_CYCLE = "ABORT_CYCLE"


class EvidenceKind(StrEnum):
    """Distinguishes observation from interpretation and quantitative claims."""

    FACT = "FACT"
    INTERPRETATION = "INTERPRETATION"
    QUANTITATIVE = "QUANTITATIVE"


class DirectionalBias(StrEnum):
    """Directional analysis without an execution instruction."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TrendStrength(StrEnum):
    """Descriptive trend-strength classification."""

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    UNCERTAIN = "UNCERTAIN"


class EntryDisposition(StrEnum):
    """Permitted Entry Analyst outcomes."""

    ENTER_NOW = "ENTER_NOW"
    WAIT_PULLBACK = "WAIT_PULLBACK"
    WAIT_BREAKOUT = "WAIT_BREAKOUT"
    NO_ENTRY = "NO_ENTRY"


class QuantEvidenceStatus(StrEnum):
    """Whether supplied evidence supports a testable hypothesis."""

    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class QuantReviewStatus(StrEnum):
    """Senior Quant review outcome for evidence and data integrity."""

    PASS = "PASS"
    CAUTION = "CAUTION"
    FAIL = "FAIL"


class SkepticVerdict(StrEnum):
    """Bounded challenge outcome from the Skeptic role."""

    APPROVE = "APPROVE"
    CAUTION = "CAUTION"
    REJECT = "REJECT"


class InformationResource(StrEnum):
    """Resources governed by the M4 information-access matrix."""

    MARKET_SNAPSHOT_VIEW = "MARKET_SNAPSHOT_VIEW"
    UPSTREAM_AGENT_OUTPUTS = "UPSTREAM_AGENT_OUTPUTS"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    QUANTITATIVE_EVIDENCE = "QUANTITATIVE_EVIDENCE"
    RISK_DECISION = "RISK_DECISION"
    PERFORMANCE_HISTORY = "PERFORMANCE_HISTORY"


class PipelineKind(StrEnum):
    """Separates current decisions from retrospective review."""

    REALTIME_DECISION = "REALTIME_DECISION"
    RETROSPECTIVE_REVIEW = "RETROSPECTIVE_REVIEW"


class PipelineComponent(StrEnum):
    """Agent and deterministic components addressable by stage definitions."""

    MARKET_CONTEXT = "MARKET_CONTEXT"
    TREND_ANALYST = "TREND_ANALYST"
    PRICE_ACTION_ANALYST = "PRICE_ACTION_ANALYST"
    ENTRY_ANALYST = "ENTRY_ANALYST"
    QUANT_RESEARCHER = "QUANT_RESEARCHER"
    SENIOR_QUANT_DEVELOPER = "SENIOR_QUANT_DEVELOPER"
    SKEPTIC = "SKEPTIC"
    CHIEF_TRADER = "CHIEF_TRADER"
    PERFORMANCE_REVIEWER = "PERFORMANCE_REVIEWER"
    RISK_ENGINE = "RISK_ENGINE"


class ModelProvider(StrEnum):
    """Vendor-neutral provider identities supported by the M5 adapter layer."""

    OPENAI = "OPENAI"
    ANTHROPIC = "ANTHROPIC"
    GEMINI = "GEMINI"
    FAKE = "FAKE"


class ReasoningEffort(StrEnum):
    """Portable requested reasoning level; providers may support only a subset."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TokenEstimateMethod(StrEnum):
    """Provenance for token counts and estimates."""

    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    PROVIDER_TOKENIZER = "PROVIDER_TOKENIZER"
    CONSERVATIVE_ESTIMATE = "CONSERVATIVE_ESTIMATE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricAvailability(StrEnum):
    """Whether a normalized telemetry value is reported, estimated, or absent."""

    REPORTED = "REPORTED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


class UsageMetric(StrEnum):
    """Provider usage fields M5 can represent without fabrication."""

    INPUT_TOKENS = "INPUT_TOKENS"
    CACHED_INPUT_TOKENS = "CACHED_INPUT_TOKENS"
    OUTPUT_TOKENS = "OUTPUT_TOKENS"
    REASONING_TOKENS = "REASONING_TOKENS"


class BudgetReservationState(StrEnum):
    """Conservative AI-budget reservation lifecycle."""

    RESERVED = "RESERVED"
    DISPATCHED = "DISPATCHED"
    SETTLED = "SETTLED"
    RELEASED = "RELEASED"
    UNCERTAIN = "UNCERTAIN"


class RuntimeFailureCategory(StrEnum):
    """Stable failure classes emitted by the single-agent M5 runtime."""

    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_PROMPT_REFERENCE = "INVALID_PROMPT_REFERENCE"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    CAPABILITY_INCOMPATIBLE = "CAPABILITY_INCOMPATIBLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    DUPLICATE_INVOCATION = "DUPLICATE_INVOCATION"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_AUTHENTICATION = "PROVIDER_AUTHENTICATION"
    PROVIDER_PERMISSION = "PROVIDER_PERMISSION"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_REFUSAL = "PROVIDER_REFUSAL"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


class CycleClaimState(StrEnum):
    """Durable lifecycle of one claimed shadow decision cycle."""

    INCOMPLETE = "INCOMPLETE"
    FINALIZED = "FINALIZED"
    ABANDONED = "ABANDONED"


class StageExecutionStatus(StrEnum):
    """Trusted orchestration result for one fixed pipeline stage."""

    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    SKIPPED = "SKIPPED"
    HOLD = "HOLD"
    ABORTED = "ABORTED"


class ShadowDisposition(StrEnum):
    """Terminal M6 outcome; none of these values represents broker execution."""

    WOULD_BUY = "WOULD_BUY"
    WOULD_SELL = "WOULD_SELL"
    CHIEF_HOLD = "CHIEF_HOLD"
    POLICY_HOLD = "POLICY_HOLD"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_HALTED = "RISK_HALTED"
    ABORTED = "ABORTED"


class ShadowOutcomeSource(StrEnum):
    """Trusted component that determined the final shadow disposition."""

    CHIEF_TRADER = "CHIEF_TRADER"
    FAILURE_POLICY = "FAILURE_POLICY"
    RISK_ENGINE = "RISK_ENGINE"
    ORCHESTRATOR = "ORCHESTRATOR"


class ShadowExecutionStatus(StrEnum):
    """The only execution status permitted in M6."""

    NOT_EXECUTED_SHADOW = "NOT_EXECUTED_SHADOW"


class QuantStageSelection(StrEnum):
    """Explicit pre-cycle selection for optional conditional quant roles."""

    SKIP = "SKIP"
    QUANT_RESEARCH_ONLY = "QUANT_RESEARCH_ONLY"
    QUANT_AND_SENIOR_REVIEW = "QUANT_AND_SENIOR_REVIEW"


class FeatureAvailability(StrEnum):
    """Availability of a structurally valid deterministic feature."""

    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNAVAILABLE = "UNAVAILABLE"


class FeatureUnit(StrEnum):
    """Units carried by numeric feature values without strategy semantics."""

    PRICE = "PRICE"
    INDEX = "INDEX"
    RATIO = "RATIO"


class FeatureWarningCode(StrEnum):
    """Non-fatal findings retained with a valid M7 feature set."""

    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"
    STALE_SOURCE = "STALE_SOURCE"


class FeatureErrorCategory(StrEnum):
    """Sanitized structural failures that prevent feature-set creation."""

    INVALID_SNAPSHOT = "INVALID_SNAPSHOT"
    INVALID_CANDLE_ORDER = "INVALID_CANDLE_ORDER"
    FUTURE_CANDLE = "FUTURE_CANDLE"
    INCOMPLETE_CANDLE = "INCOMPLETE_CANDLE"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    CONFIGURATION_INCOMPATIBLE = "CONFIGURATION_INCOMPATIBLE"
    CALCULATION_FAILURE = "CALCULATION_FAILURE"


class DatasetPartitionKind(StrEnum):
    """Immutable purpose of one historical dataset partition."""

    RESEARCH = "RESEARCH"
    VALIDATION = "VALIDATION"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"


class ReplayDecisionSource(StrEnum):
    """Non-provider source of a frozen historical proposal."""

    SCRIPTED = "SCRIPTED"
    SYNTHETIC = "SYNTHETIC"
    FAKE_RUNTIME = "FAKE_RUNTIME"
    PERSISTED_RECORD = "PERSISTED_RECORD"


class EntryActivationPolicy(StrEnum):
    """Explicit theoretical entry assumption used by M8."""

    ACTIVE_AT_DECISION_CUTOFF = "ACTIVE_AT_DECISION_CUTOFF"


class IntrabarPolicy(StrEnum):
    """Treatment of unknowable event ordering inside one OHLC candle."""

    MARK_AMBIGUOUS = "MARK_AMBIGUOUS"


class OutcomeBasis(StrEnum):
    """Execution/cost meaning of an M8 price-path outcome."""

    THEORETICAL_LEVEL_TOUCH_NO_COSTS = "THEORETICAL_LEVEL_TOUCH_NO_COSTS"


class TradeOutcomeStatus(StrEnum):
    """Terminal state of one finite historical price-path evaluation."""

    TAKE_PROFIT_REACHED = "TAKE_PROFIT_REACHED"
    STOP_LOSS_REACHED = "STOP_LOSS_REACHED"
    UNRESOLVED_HORIZON = "UNRESOLVED_HORIZON"
    AMBIGUOUS_INTRABAR = "AMBIGUOUS_INTRABAR"


class ResearchMetricStatus(StrEnum):
    """Availability semantics for finite Decimal research metrics."""

    VALID = "VALID"
    UNAVAILABLE = "UNAVAILABLE"
    UNBOUNDED = "UNBOUNDED"


class SegmentDimension(StrEnum):
    """Predeclared immutable facts allowed for descriptive grouping."""

    DIRECTION = "DIRECTION"
    TIMEFRAME = "TIMEFRAME"
    PARTITION = "PARTITION"
    FEATURE_REGIME = "FEATURE_REGIME"
    VOLATILITY_BUCKET = "VOLATILITY_BUCKET"
    TREND_STRENGTH_BUCKET = "TREND_STRENGTH_BUCKET"
    CHIEF_DECISION = "CHIEF_DECISION"
    SKEPTIC_DECISION = "SKEPTIC_DECISION"


class ReplayErrorCategory(StrEnum):
    """Sanitized failures that prevent a valid replay artifact."""

    INVALID_DATASET = "INVALID_DATASET"
    DATASET_DIGEST_MISMATCH = "DATASET_DIGEST_MISMATCH"
    PARTITION_VIOLATION = "PARTITION_VIOLATION"
    INVALID_REPLAY_CLOCK = "INVALID_REPLAY_CLOCK"
    FUTURE_DATA_ACCESS = "FUTURE_DATA_ACCESS"
    MISSING_AS_OF_OBSERVATION = "MISSING_AS_OF_OBSERVATION"
    SNAPSHOT_REPRODUCTION_FAILURE = "SNAPSHOT_REPRODUCTION_FAILURE"
    FEATURE_REPRODUCTION_FAILURE = "FEATURE_REPRODUCTION_FAILURE"
    DECISION_NOT_FROZEN = "DECISION_NOT_FROZEN"
    INVALID_PROPOSAL = "INVALID_PROPOSAL"
    INVALID_RISK_LINKAGE = "INVALID_RISK_LINKAGE"
    INVALID_OUTCOME_DATA = "INVALID_OUTCOME_DATA"
    INVALID_HORIZON = "INVALID_HORIZON"
    DUPLICATE_REPLAY_RECORD = "DUPLICATE_REPLAY_RECORD"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
