from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from tests.fakes.risk import EVALUATED_AT, account_context, proposal, risk_snapshot

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.enums import (
    PositionSizingStatus,
    RiskDecisionStatus,
    RiskReasonCode,
    RiskState,
    TradeSide,
)


def test_valid_buy_is_approved_with_auditable_size() -> None:
    snapshot = risk_snapshot()
    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, account_context(snapshot), EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.risk_state is RiskState.NORMAL
    assert not decision.reasons
    assert decision.position_sizing is not None
    assert decision.position_sizing.status is PositionSizingStatus.APPROVED
    assert decision.position_sizing.selected_volume == Decimal("0.01")
    assert decision.position_sizing.estimated_risk_amount == Decimal("0.20")
    assert decision.position_sizing.allowed_risk_amount == Decimal("0.25")


def test_valid_sell_is_approved() -> None:
    snapshot = risk_snapshot()
    candidate = proposal(
        side=TradeSide.SELL,
        stop_loss=Decimal("1.08150"),
        take_profit=Decimal("1.08100"),
    )

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        candidate, snapshot, account_context(snapshot), EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.APPROVED


def test_missing_stop_loss_is_rejected_without_sizing() -> None:
    snapshot = risk_snapshot()
    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(stop_loss=None), snapshot, account_context(snapshot), EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.position_sizing is None
    assert RiskReasonCode.STOP_LOSS_REQUIRED in tuple(
        reason.code for reason in decision.reasons
    )


def test_minimum_broker_volume_exceeding_risk_rejects_final_decision() -> None:
    snapshot = risk_snapshot()
    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(stop_loss=Decimal("1.08030"), take_profit=Decimal("1.08280")),
        snapshot,
        account_context(snapshot),
        EVALUATED_AT,
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.position_sizing is not None
    assert decision.position_sizing.status is PositionSizingStatus.REJECTED
    assert decision.reasons[0].code is RiskReasonCode.MINIMUM_VOLUME_EXCEEDS_RISK


def test_daily_loss_breach_produces_halted_decision() -> None:
    snapshot = risk_snapshot(equity=Decimal("97"))
    context = account_context(
        snapshot,
        peak_equity=Decimal("97"),
        day_start_equity=Decimal("100"),
    )

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, context, EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.HALTED
    assert decision.risk_state is RiskState.HALTED
    assert decision.position_sizing is None


def test_maximum_position_count_rejects_without_halting_account_state() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot, open_position_count=1)

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, context, EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.risk_state is RiskState.NORMAL
    assert decision.reasons[0].code is RiskReasonCode.MAXIMUM_POSITIONS_REACHED


def test_account_context_and_snapshot_mismatch_is_rejected() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot, account_ref="acct-v1:" + "f" * 64)

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, context, EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert RiskReasonCode.ACCOUNT_CONTEXT_MISMATCH in tuple(
        reason.code for reason in decision.reasons
    )


def test_evaluation_timestamp_must_not_predate_inputs() -> None:
    snapshot = risk_snapshot()

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(),
        snapshot,
        account_context(snapshot),
        snapshot.snapshot_completed_at - timedelta(seconds=1),
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert RiskReasonCode.ACCOUNT_CONTEXT_FUTURE_DATED in tuple(
        reason.code for reason in decision.reasons
    )
    assert RiskReasonCode.EVALUATION_TIMESTAMP_INVALID in tuple(
        reason.code for reason in decision.reasons
    )


def test_naive_evaluation_timestamp_is_rejected_at_the_boundary() -> None:
    snapshot = risk_snapshot()

    with pytest.raises(ValueError, match="timezone-aware"):
        RiskEngine(RiskConstitutionSettings()).evaluate(
            proposal(), snapshot, account_context(snapshot), datetime(2026, 9, 10)
        )


def test_same_explicit_inputs_produce_byte_identical_decisions() -> None:
    snapshot = risk_snapshot()
    candidate = proposal()
    context = account_context(snapshot)
    engine = RiskEngine(RiskConstitutionSettings())

    first = engine.evaluate(candidate, snapshot, context, EVALUATED_AT)
    second = engine.evaluate(candidate, snapshot, context, EVALUATED_AT)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_safe_mode_uses_minimum_configured_risk_without_ai_input() -> None:
    snapshot = risk_snapshot(equity=Decimal("92"))
    context = account_context(
        snapshot, peak_equity=Decimal("100"), day_start_equity=Decimal("92")
    )

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, context, EVALUATED_AT
    )

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.risk_state is RiskState.SAFE_MODE
    assert decision.account_metrics.permitted_risk_percent == Decimal("0.25")
    assert decision.position_sizing is not None
    assert decision.position_sizing.risk_percent == Decimal("0.25")
