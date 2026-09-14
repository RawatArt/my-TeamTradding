"""M11 SQLite audit, unique-claim, and restart recovery tests."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.fakes.execution import EXECUTION_AT, execution_bundle

from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    DemoExecutionState,
    ExecutionControlState,
)
from ai_trading_team.schemas.execution import ExecutionControlEvent
from ai_trading_team.storage.execution import SQLiteDemoExecutionRepository


def test_sqlite_claim_is_unique_and_restart_abandons_pre_dispatch_work(tmp_path: Path) -> None:
    service, candidate, acceptance, policy, memory, _ = execution_bundle()
    complete = service.execute(candidate, acceptance, policy, claim_owner="fixture-owner")
    approval = memory.effective_approvals(
        account_ref=acceptance.account_ref,
        environment_ref=acceptance.environment_ref,
        symbol=acceptance.symbol,
        at=EXECUTION_AT,
    )[0]
    path = tmp_path / "m11-execution.sqlite3"
    repository = SQLiteDemoExecutionRepository(path)
    repository.add_environment_acceptance(acceptance)
    repository.add_approval(approval)
    repository.append_control_event(
        ExecutionControlEvent(
            event_id="sqlite-control-disabled-m11",
            previous_state=None,
            state=ExecutionControlState.DISABLED,
            operator_ref="operator-reviewer-m11",
            occurred_at=EXECUTION_AT - timedelta(seconds=2),
            reason="safe default",
        )
    )
    repository.append_control_event(
        ExecutionControlEvent(
            event_id="sqlite-control-enabled-m11",
            previous_state=ExecutionControlState.DISABLED,
            state=ExecutionControlState.ENABLED,
            operator_ref="operator-reviewer-m11",
            occurred_at=EXECUTION_AT - timedelta(seconds=1),
            reason="explicit test enablement",
        )
    )
    assert complete.preflight is not None
    assert complete.risk_revalidation is not None
    claimed = repository.claim(
        complete.intent,
        complete.preflight,
        complete.risk_revalidation,
        "sqlite-owner",
        complete.events[1].occurred_at,
    )
    with pytest.raises(DemoExecutionError) as captured:
        repository.claim(
            complete.intent,
            complete.preflight,
            complete.risk_revalidation,
            "duplicate-owner",
            complete.events[1].occurred_at,
        )
    assert captured.value.category is DemoExecutionFailureCategory.DUPLICATE_EXECUTION_INTENT
    repository.close()

    reopened = SQLiteDemoExecutionRepository(path)
    loaded = reopened.get(claimed.intent.execution_intent_id)
    assert loaded == claimed
    recovered = reopened.recover_incomplete(EXECUTION_AT + timedelta(seconds=2))
    assert recovered[0].state is DemoExecutionState.REJECTED
    assert recovered[0].events[-1].failure is not None
    assert (
        recovered[0].events[-1].failure.code
        is DemoExecutionFailureCategory.PROCESS_RESTART
    )
    reopened.close()
