"""Composite broker reconciliation without comment/magic identity assumptions."""

from datetime import datetime

from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    DemoReconciliationStatus,
    TradeSide,
)
from ai_trading_team.schemas.execution import (
    CompositeBrokerEvidence,
    DemoExecutionFailure,
    DemoOrderIntent,
    DemoReconciliationRecord,
    DemoSubmissionReceipt,
)


def reconcile_broker_evidence(
    intent: DemoOrderIntent,
    receipt: DemoSubmissionReceipt,
    evidence: tuple[CompositeBrokerEvidence, ...],
    *,
    reconciled_at: datetime,
) -> DemoReconciliationRecord:
    """Require one exact composite match; broker correlation text is only supporting evidence."""
    if not evidence:
        return _failure(
            intent,
            DemoReconciliationStatus.NOT_FOUND,
            DemoExecutionFailureCategory.RECONCILIATION_TIMEOUT,
            "no conclusive broker evidence was found; submission remains uncertain",
            reconciled_at,
        )
    if len(evidence) != 1:
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.BROKER_IDENTITY_MISMATCH,
            "broker reconciliation returned multiple candidate executions",
            reconciled_at,
            evidence,
        )
    item = evidence[0]
    base_identity_matches = (
        item.account_ref == intent.account_ref,
        item.environment_ref == intent.environment_ref,
        item.symbol == intent.symbol,
        item.side is intent.side,
        item.dispatch_started_at >= receipt.dispatch_started_at,
        item.dispatch_completed_at <= item.observed_at,
        item.broker_order_id is not None or item.broker_deal_id is not None,
        item.resulting_position_id is not None,
    )
    if all(base_identity_matches) and item.volume != intent.volume:
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.PARTIAL_FILL,
            "broker evidence volume differs from the sealed all-or-nothing intent",
            reconciled_at,
            evidence,
        )
    identity_matches = (
        *base_identity_matches[:4],
        item.volume == intent.volume,
        *base_identity_matches[4:],
    )
    if not all(identity_matches):
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.BROKER_IDENTITY_MISMATCH,
            "composite broker identity differs from the sealed intent",
            reconciled_at,
            evidence,
        )
    if item.fill_price is None:
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.RECONCILIATION_FAILED,
            "broker evidence has no confirmed fill price",
            reconciled_at,
            evidence,
        )
    adverse_fill = (
        item.fill_price > intent.risk_validation_price
        if intent.side is TradeSide.BUY
        else item.fill_price < intent.risk_validation_price
    )
    if adverse_fill:
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.FILL_OUTSIDE_POLICY,
            "confirmed fill exceeded the M3 worst-case risk-validation price",
            reconciled_at,
            evidence,
        )
    if item.stop_loss != intent.stop_loss or item.take_profit != intent.take_profit:
        return _failure(
            intent,
            DemoReconciliationStatus.MISMATCH,
            DemoExecutionFailureCategory.PROTECTIVE_LEVEL_MISMATCH,
            "broker position does not retain the mandatory sealed SL and TP",
            reconciled_at,
            evidence,
        )
    return DemoReconciliationRecord(
        execution_intent_id=intent.execution_intent_id,
        intent_digest=intent.intent_digest,
        status=DemoReconciliationStatus.CONFIRMED,
        reconciled_at=reconciled_at,
        evidence=evidence,
    )


def _failure(
    intent: DemoOrderIntent,
    status: DemoReconciliationStatus,
    category: DemoExecutionFailureCategory,
    detail: str,
    reconciled_at: datetime,
    evidence: tuple[CompositeBrokerEvidence, ...] = (),
) -> DemoReconciliationRecord:
    return DemoReconciliationRecord(
        execution_intent_id=intent.execution_intent_id,
        intent_digest=intent.intent_digest,
        status=status,
        reconciled_at=reconciled_at,
        evidence=evidence,
        failure=DemoExecutionFailure(code=category, sanitized_detail=detail),
    )
