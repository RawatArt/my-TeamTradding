"""Deterministic M6 input compatibility checks performed before provider dispatch."""

from datetime import UTC, datetime

from ai_trading_team.risk.account import account_fingerprint
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import AccountRiskContext


class ShadowPreflightError(ValueError):
    """Raised for a structural cycle/snapshot/account incompatibility."""


def validate_shadow_inputs(
    snapshot: MarketSnapshot,
    context: AccountRiskContext,
    evaluated_at: datetime,
) -> None:
    """Validate identity and time only; all risk calculations remain in M3."""
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ShadowPreflightError("preflight timestamp must be timezone-aware")
    moment = evaluated_at.astimezone(UTC)
    if context.cycle_id != snapshot.cycle_id or context.snapshot_id != snapshot.snapshot_id:
        raise ShadowPreflightError("account context does not match the snapshot trace")
    expected_ref = account_fingerprint(snapshot.account.account_id, snapshot.account.server)
    if context.account_ref != expected_ref:
        raise ShadowPreflightError("account context does not match the snapshot account")
    if snapshot.snapshot_completed_at > moment:
        raise ShadowPreflightError("snapshot completion is later than preflight time")
    if context.context_as_of > moment:
        raise ShadowPreflightError("account context is later than preflight time")
    if context.context_as_of < snapshot.snapshot_completed_at:
        raise ShadowPreflightError("account context predates snapshot completion")
    if context.trading_day_started_at > context.context_as_of:
        raise ShadowPreflightError("trading-day context is temporally inconsistent")
