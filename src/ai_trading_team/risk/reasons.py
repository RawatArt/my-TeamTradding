"""Stable, sanitized reasons emitted by the deterministic Risk Engine."""

from ai_trading_team.schemas.enums import RiskReasonCode
from ai_trading_team.schemas.risk import RiskReason


def risk_reason(code: RiskReasonCode, message: str) -> RiskReason:
    """Build one immutable reason without attaching sensitive broker metadata."""
    return RiskReason(code=code, message=message)
