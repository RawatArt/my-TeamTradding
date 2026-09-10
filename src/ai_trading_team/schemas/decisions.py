"""Minimal decision and risk-evaluation contracts without executable order fields."""

from ai_trading_team.schemas.common import (
    Confidence,
    FiniteDecimal,
    Identifier,
    Symbol,
    TraceableRecord,
)
from ai_trading_team.schemas.enums import RiskDecisionStatus, TradeAction, TradeSide


class TradeProposal(TraceableRecord):
    """An AI-originated proposal that has no execution authority or position size."""

    proposal_id: Identifier
    symbol: Symbol
    side: TradeSide
    entry: FiniteDecimal | None = None
    stop_loss: FiniteDecimal | None = None
    take_profit: FiniteDecimal | None = None
    rationale: str


class ChiefDecision(TraceableRecord):
    """A traceable BUY/SELL/HOLD decision; it is not an order."""

    action: TradeAction
    confidence: Confidence
    rationale: str
    proposal_id: Identifier | None = None


class RiskEvaluation(TraceableRecord):
    """Result boundary for a future deterministic engine; no engine exists in M0."""

    proposal_id: Identifier
    status: RiskDecisionStatus
    reasons: tuple[str, ...]

