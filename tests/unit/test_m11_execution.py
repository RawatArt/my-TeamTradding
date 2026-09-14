"""M11 one-shot DEMO execution state-machine and guard tests."""

from datetime import timedelta
from decimal import Decimal

import pytest
from tests.fakes.execution import EXECUTION_AT, FakeDemoExecutionAdapter, execution_bundle
from tests.fakes.market import position

from ai_trading_team.execution.errors import DemoExecutionError
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import (
    DemoExecutionFailureCategory,
    DemoExecutionState,
    DemoSubmissionDisposition,
    ExecutionControlState,
    ExecutionSnapshotPurpose,
)
from ai_trading_team.schemas.execution import (
    DemoExecutionApprovalRevocation,
    DemoExecutionRecord,
    ExecutionControlEvent,
    FinalDispatchObservation,
)


def _failure_code(record: DemoExecutionRecord) -> DemoExecutionFailureCategory | None:
    failure = record.events[-1].failure
    return None if failure is None else failure.code


def _replace_final(adapter: FakeDemoExecutionAdapter, **changes: object) -> None:
    current = adapter.final_observation
    payload = current.model_dump(mode="python")
    payload.update(changes)
    adapter.final_observation = FinalDispatchObservation.model_validate(payload)


def test_fake_adapter_executes_one_protected_demo_submission_exactly_once() -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert record.state is DemoExecutionState.CONFIRMED
    assert [event.state for event in record.events] == [
        DemoExecutionState.CREATED,
        DemoExecutionState.CLAIMED,
        DemoExecutionState.DISPATCHING,
        DemoExecutionState.SUBMITTED,
        DemoExecutionState.CONFIRMED,
    ]
    assert adapter.check_calls == 1
    assert adapter.submit_calls == 1
    assert adapter.reconcile_calls == 1
    assert record.intent.stop_loss is not None
    assert record.intent.take_profit is not None


def test_order_check_success_does_not_imply_submission_when_final_guard_fails() -> None:
    service, candidate, acceptance, policy, repository, adapter = execution_bundle()
    adapter.after_check = lambda: repository.append_control_event(
        ExecutionControlEvent(
            event_id="pause-after-order-check-m11",
            previous_state=ExecutionControlState.ENABLED,
            state=ExecutionControlState.PAUSED,
            operator_ref="operator-reviewer-m11",
            occurred_at=EXECUTION_AT + timedelta(milliseconds=200),
            reason="operator pause before broker mutation",
        )
    )

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert record.state is DemoExecutionState.REJECTED
    assert _failure_code(record) is DemoExecutionFailureCategory.EXECUTION_PAUSED
    assert adapter.check_calls == 1
    assert adapter.submit_calls == 0
    assert DemoExecutionState.SUBMITTED not in {event.state for event in record.events}
    assert DemoExecutionState.CONFIRMED not in {event.state for event in record.events}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("account", DemoExecutionFailureCategory.ACCOUNT_MISMATCH),
        ("position", DemoExecutionFailureCategory.OPEN_POSITION_CONFLICT),
        ("stale_tick", DemoExecutionFailureCategory.STALE_EXECUTION_TICK),
        ("spread", DemoExecutionFailureCategory.SPREAD_LIMIT_EXCEEDED),
        ("price_drift", DemoExecutionFailureCategory.PRICE_DRIFT_EXCEEDED),
        ("capability", DemoExecutionFailureCategory.BROKER_METADATA_CHANGED),
    ],
)
def test_final_dispatch_guard_blocks_changed_broker_state(
    mutation: str,
    expected: DemoExecutionFailureCategory,
) -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()
    final = adapter.final_observation
    if mutation == "account":
        _replace_final(adapter, account_ref="acct-v1:" + "f" * 64)
    elif mutation == "position":
        _replace_final(adapter, positions=(position(symbol=candidate.decision.symbol),))
    elif mutation == "stale_tick":
        tick = final.tick.model_copy(
            update={"source_time": EXECUTION_AT - timedelta(seconds=10)}
        )
        _replace_final(adapter, tick=tick)
    elif mutation == "spread":
        tick = final.tick.model_copy(
            update={
                "bid": Decimal("1.08000"),
                "ask": Decimal("1.08130"),
                "spread": Decimal("0.00130"),
            }
        )
        _replace_final(adapter, tick=tick)
    elif mutation == "price_drift":
        tick = final.tick.model_copy(
            update={
                "bid": Decimal("1.08140"),
                "ask": Decimal("1.08150"),
                "spread": Decimal("0.00010"),
            }
        )
        _replace_final(adapter, tick=tick)
    else:
        capabilities = final.capabilities.model_copy(
            update={"market_order_allowed": False}
        )
        _replace_final(adapter, capabilities=capabilities)

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert record.state is DemoExecutionState.REJECTED
    assert _failure_code(record) is expected
    assert adapter.submit_calls == 0


def test_final_dispatch_guard_blocks_revoked_human_approval() -> None:
    service, candidate, acceptance, policy, repository, adapter = execution_bundle()
    approval = repository.effective_approvals(
        account_ref=acceptance.account_ref,
        environment_ref=acceptance.environment_ref,
        symbol=acceptance.symbol,
        at=EXECUTION_AT,
    )[0]
    adapter.after_check = lambda: repository.revoke_approval(
        DemoExecutionApprovalRevocation(
            revocation_id="revocation-after-check-m11",
            approval_id=approval.approval_id,
            approval_digest=content_digest(approval),
            reviewer_ref="operator-reviewer-m11",
            revoked_at=EXECUTION_AT + timedelta(milliseconds=200),
            reason="human approval revoked before dispatch",
        )
    )

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert _failure_code(record) is DemoExecutionFailureCategory.APPROVAL_REVOKED
    assert adapter.submit_calls == 0


def test_duplicate_source_intent_never_dispatches_twice() -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()
    first = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    with pytest.raises(DemoExecutionError) as captured:
        service.execute(candidate, acceptance, policy, claim_owner="worker-m11-second")

    assert first.state is DemoExecutionState.CONFIRMED
    assert captured.value.category is DemoExecutionFailureCategory.DUPLICATE_EXECUTION_INTENT
    assert adapter.submit_calls == 1


def test_dispatch_timeout_becomes_unknown_and_reconciliation_never_resubmits() -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()
    adapter.raise_on_submit = True
    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")
    assert record.state is DemoExecutionState.UNKNOWN
    assert adapter.submit_calls == 1

    adapter.raise_on_submit = False
    reconciled = service.reconcile_unknown(record.intent.execution_intent_id)

    assert reconciled.state is DemoExecutionState.CONFIRMED
    assert adapter.submit_calls == 1
    assert adapter.reconcile_calls == 1


def test_reconciliation_uses_composite_evidence_not_comment_or_magic_alone() -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert record.state is DemoExecutionState.CONFIRMED
    evidence = record.reconciliation
    assert evidence is not None
    assert evidence.evidence[0].comment == "broker-truncated"
    assert evidence.evidence[0].magic != record.intent.magic


def test_analysis_and_execution_snapshots_are_distinct_and_original_is_unchanged() -> None:
    service, candidate, acceptance, policy, _, _ = execution_bundle()
    original = candidate.model_dump_json()

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    link = record.intent.snapshot_link
    assert link.analysis_snapshot_id == candidate.decision.actual_snapshot_id
    assert link.execution_snapshot_id != link.analysis_snapshot_id
    assert link.purpose is ExecutionSnapshotPurpose.PRE_SEND_REVALIDATION
    assert candidate.model_dump_json() == original


def test_definitive_broker_rejection_is_terminal_without_reconciliation() -> None:
    service, candidate, acceptance, policy, _, adapter = execution_bundle()
    adapter.submission_disposition = DemoSubmissionDisposition.REJECTED

    record = service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    assert record.state is DemoExecutionState.REJECTED
    assert _failure_code(record) is DemoExecutionFailureCategory.BROKER_REJECTED
    assert adapter.submit_calls == 1
    assert adapter.reconcile_calls == 0


def test_process_crash_at_dispatching_recovers_unknown_and_never_resubmits() -> None:
    service, candidate, acceptance, policy, repository, adapter = execution_bundle()
    shadow = candidate.decision.shadow_record
    assert shadow is not None and shadow.shadow_trade_intent is not None
    source_digest = content_digest(shadow.shadow_trade_intent)
    adapter.crash_on_submit = True

    with pytest.raises(KeyboardInterrupt):
        service.execute(candidate, acceptance, policy, claim_owner="worker-m11")

    dispatching = repository.get_by_source_digest(source_digest)
    assert dispatching is not None
    assert dispatching.state is DemoExecutionState.DISPATCHING
    assert adapter.submit_calls == 1

    recovered = repository.recover_incomplete(
        EXECUTION_AT + timedelta(milliseconds=450)
    )
    assert len(recovered) == 1
    assert recovered[0].state is DemoExecutionState.UNKNOWN
    adapter.crash_on_submit = False
    reconciled = service.reconcile_unknown(recovered[0].intent.execution_intent_id)

    assert reconciled.state is DemoExecutionState.CONFIRMED
    assert adapter.submit_calls == 1


def test_execution_records_preserve_decimal_strings_and_repeat_deterministically() -> None:
    service_a, candidate_a, acceptance_a, policy_a, _, _ = execution_bundle()
    service_b, candidate_b, acceptance_b, policy_b, _, _ = execution_bundle()

    first = service_a.execute(
        candidate_a, acceptance_a, policy_a, claim_owner="worker-m11"
    )
    second = service_b.execute(
        candidate_b, acceptance_b, policy_b, claim_owner="worker-m11"
    )

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert '"volume":"0.01"' in first.model_dump_json()
    assert '"reference_price":"1.08130"' in first.model_dump_json()
