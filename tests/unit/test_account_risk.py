from datetime import timedelta
from decimal import Decimal

import pytest
from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import AccountRiskEvaluator
from ai_trading_team.risk.account import AccountRiskAssessment
from ai_trading_team.schemas.enums import RiskReasonCode, RiskState


def evaluate(
    *,
    equity: Decimal,
    peak: Decimal,
    day_start: Decimal | None = None,
    position_count: int = 0,
) -> AccountRiskAssessment:
    snapshot = risk_snapshot(equity=equity)
    context = account_context(
        snapshot,
        peak_equity=peak,
        day_start_equity=day_start or equity,
        open_position_count=position_count,
    )
    return AccountRiskEvaluator(RiskConstitutionSettings()).evaluate(
        snapshot, context, EVALUATED_AT
    )


@pytest.mark.parametrize(
    ("equity", "expected"),
    [
        (Decimal("96"), RiskState.NORMAL),
        (Decimal("95"), RiskState.CAUTION),
        (Decimal("92"), RiskState.SAFE_MODE),
        (Decimal("85"), RiskState.HALTED),
    ],
)
def test_cash_flow_adjusted_drawdown_transitions(
    equity: Decimal, expected: RiskState
) -> None:
    assessment = evaluate(equity=equity, peak=Decimal("100"))

    assert assessment.state is expected


def test_new_equity_high_updates_effective_peak_without_drawdown() -> None:
    assessment = evaluate(equity=Decimal("110"), peak=Decimal("100"))

    assert assessment.metrics.effective_peak_equity == Decimal("110")
    assert assessment.metrics.drawdown_amount == 0
    assert assessment.metrics.drawdown_percent == 0


def test_daily_loss_limit_halts_independently_of_drawdown_baseline() -> None:
    assessment = evaluate(
        equity=Decimal("97"), peak=Decimal("97"), day_start=Decimal("100")
    )

    assert assessment.state is RiskState.HALTED
    assert RiskReasonCode.DAILY_LOSS_LIMIT_REACHED in tuple(
        reason.code for reason in assessment.reasons
    )
    assert assessment.metrics.daily_loss_percent == Decimal("3.00")


def test_maximum_drawdown_halt_is_explained() -> None:
    assessment = evaluate(equity=Decimal("84"), peak=Decimal("100"))

    assert assessment.state is RiskState.HALTED
    assert RiskReasonCode.MAXIMUM_DRAWDOWN_REACHED in tuple(
        reason.code for reason in assessment.reasons
    )


def test_maximum_account_wide_position_limit_is_rejected() -> None:
    assessment = evaluate(equity=Decimal("100"), peak=Decimal("100"), position_count=1)

    assert assessment.state is RiskState.NORMAL
    assert assessment.reasons[0].code is RiskReasonCode.MAXIMUM_POSITIONS_REACHED


def test_future_dated_context_is_rejected_deterministically() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot, context_as_of=EVALUATED_AT + timedelta(seconds=1))

    assessment = AccountRiskEvaluator(RiskConstitutionSettings()).evaluate(
        snapshot, context, EVALUATED_AT
    )

    assert RiskReasonCode.ACCOUNT_CONTEXT_FUTURE_DATED in tuple(
        reason.code for reason in assessment.reasons
    )


def test_account_fingerprint_mismatch_is_rejected_without_raw_identifier() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot, account_ref="acct-v1:" + "0" * 64)

    assessment = AccountRiskEvaluator(RiskConstitutionSettings()).evaluate(
        snapshot, context, EVALUATED_AT
    )

    mismatch = next(
        reason
        for reason in assessment.reasons
        if reason.code is RiskReasonCode.ACCOUNT_CONTEXT_MISMATCH
    )
    assert str(snapshot.account.account_id) not in mismatch.message
    assert snapshot.account.server not in mismatch.message


def test_snapshot_symbol_position_count_cannot_exceed_account_wide_count() -> None:
    from tests.fakes.market import position

    snapshot = risk_snapshot(positions=(position(),))
    context = account_context(snapshot, open_position_count=0)

    assessment = AccountRiskEvaluator(RiskConstitutionSettings()).evaluate(
        snapshot, context, EVALUATED_AT
    )

    assert RiskReasonCode.ACCOUNT_POSITION_COUNT_INCONSISTENT in tuple(
        reason.code for reason in assessment.reasons
    )
