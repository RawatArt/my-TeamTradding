from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes.risk import CYCLE_ID, EVALUATED_AT
from tests.fakes.runtime import budget_policy, pricing_profile, runtime_profile

from ai_trading_team.runtime.budget import BudgetGuard, InMemoryBudgetLedger
from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.enums import BudgetReservationState, TokenEstimateMethod
from ai_trading_team.schemas.runtime import TokenEstimate
from ai_trading_team.storage import SQLiteBudgetLedger


def estimate(tokens: int = 100) -> TokenEstimate:
    return TokenEstimate(
        tokens=tokens,
        method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
        conservative=True,
        estimated_at=EVALUATED_AT,
    )


def test_budget_reserves_before_dispatch_and_settles_after_reported_usage() -> None:
    ledger = InMemoryBudgetLedger()
    guard = BudgetGuard(ledger)
    reservation = guard.reserve(
        invocation_id="invocation-budget-001",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )

    assert reservation.state is BudgetReservationState.RESERVED
    assert guard.mark_dispatched(reservation.invocation_id, at=EVALUATED_AT).state is (
        BudgetReservationState.DISPATCHED
    )
    settled = guard.settle(
        reservation.invocation_id,
        Decimal("0.0001"),
        at=EVALUATED_AT,
    )
    assert settled.state is BudgetReservationState.SETTLED


def test_dispatched_reservation_cannot_be_released() -> None:
    ledger = InMemoryBudgetLedger()
    guard = BudgetGuard(ledger)
    reservation = guard.reserve(
        invocation_id="invocation-budget-002",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    guard.mark_dispatched(reservation.invocation_id, at=EVALUATED_AT)

    with pytest.raises(ValueError, match="RESERVED"):
        guard.release(reservation.invocation_id, at=EVALUATED_AT)


def test_timeout_or_unknown_billing_retains_uncertain_reservation() -> None:
    ledger = InMemoryBudgetLedger()
    guard = BudgetGuard(ledger)
    reservation = guard.reserve(
        invocation_id="invocation-budget-003",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    guard.mark_dispatched(reservation.invocation_id, at=EVALUATED_AT)

    uncertain = guard.mark_uncertain(reservation.invocation_id, at=EVALUATED_AT)
    assert uncertain.state is BudgetReservationState.UNCERTAIN
    assert uncertain.reserved_amount == reservation.reserved_amount


def test_duplicate_invocation_id_is_rejected_before_second_dispatch() -> None:
    ledger = InMemoryBudgetLedger()
    guard = BudgetGuard(ledger)
    guard.reserve(
        invocation_id="invocation-duplicate",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )

    with pytest.raises(RuntimeInvocationError, match="already"):
        guard.reserve(
            invocation_id="invocation-duplicate",
            cycle_id=CYCLE_ID,
            runtime=runtime_profile(),
            capability_input_estimate=estimate(),
            policy=budget_policy(),
            pricing=pricing_profile(),
            at=EVALUATED_AT,
        )


def test_distinct_retry_attempt_is_reserved_under_same_logical_invocation() -> None:
    ledger = InMemoryBudgetLedger()
    guard = BudgetGuard(ledger)
    first = guard.reserve(
        invocation_id="invocation-attempts",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    guard.mark_dispatched(first.invocation_id, at=EVALUATED_AT)
    guard.mark_uncertain(first.invocation_id, at=EVALUATED_AT)

    second = guard.reserve(
        invocation_id=first.invocation_id,
        attempt_number=2,
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )

    assert second.attempt_number == 2
    assert len(ledger.attempts(first.invocation_id)) == 2


def test_budget_rejects_unavailable_estimate_and_per_call_excess() -> None:
    guard = BudgetGuard(InMemoryBudgetLedger())
    unavailable = TokenEstimate(
        tokens=None,
        method=TokenEstimateMethod.UNAVAILABLE,
        conservative=False,
        estimated_at=EVALUATED_AT,
    )
    with pytest.raises(RuntimeInvocationError, match="unavailable"):
        guard.reserve(
            invocation_id="invocation-unavailable",
            cycle_id=CYCLE_ID,
            runtime=runtime_profile(),
            capability_input_estimate=unavailable,
            policy=budget_policy(),
            pricing=pricing_profile(),
            at=EVALUATED_AT,
        )


def test_sqlite_ledger_persists_identity_and_state(tmp_path: Path) -> None:
    path = tmp_path / "budget.sqlite3"
    ledger = SQLiteBudgetLedger(path)
    guard = BudgetGuard(ledger)
    reservation = guard.reserve(
        invocation_id="invocation-persistent",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    guard.mark_dispatched(reservation.invocation_id, at=EVALUATED_AT + timedelta(seconds=1))
    ledger.close()

    reopened = SQLiteBudgetLedger(path)
    assert reopened.get(reservation.invocation_id).state is BudgetReservationState.DISPATCHED  # type: ignore[union-attr]
    with pytest.raises(RuntimeInvocationError, match="already"):
        BudgetGuard(reopened).reserve(
            invocation_id=reservation.invocation_id,
            cycle_id=CYCLE_ID,
            runtime=runtime_profile(),
            capability_input_estimate=estimate(),
            policy=budget_policy(),
            pricing=pricing_profile(),
            at=EVALUATED_AT,
        )
    reopened.close()


def test_sqlite_ledger_persists_distinct_attempts_for_one_invocation(tmp_path: Path) -> None:
    path = tmp_path / "attempts.sqlite3"
    ledger = SQLiteBudgetLedger(path)
    guard = BudgetGuard(ledger)
    first = guard.reserve(
        invocation_id="invocation-sqlite-attempts",
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    guard.mark_dispatched(first.invocation_id, at=EVALUATED_AT)
    guard.mark_uncertain(first.invocation_id, at=EVALUATED_AT)
    guard.reserve(
        invocation_id=first.invocation_id,
        attempt_number=2,
        cycle_id=CYCLE_ID,
        runtime=runtime_profile(),
        capability_input_estimate=estimate(),
        policy=budget_policy(),
        pricing=pricing_profile(),
        at=EVALUATED_AT,
    )
    ledger.close()

    reopened = SQLiteBudgetLedger(path)
    attempts = reopened.attempts(first.invocation_id)
    assert [item.attempt_number for item in attempts] == [1, 2]
    assert attempts[0].state is BudgetReservationState.UNCERTAIN
    assert attempts[1].state is BudgetReservationState.RESERVED
    reopened.close()
