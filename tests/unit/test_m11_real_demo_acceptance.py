"""M11 real-DEMO addendum tests; all execution uses the broker-free fake adapter."""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from tests.fakes.execution import EXECUTION_AT, IncrementingClock, execution_bundle

from ai_trading_team.execution.real_demo_acceptance import RealDemoAcceptanceCoordinator
from ai_trading_team.execution.vendor_boundary import build_vendor_boundary_audit
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import DemoExecutionState, ExecutionControlState
from ai_trading_team.schemas.execution import ExecutionControlEvent
from ai_trading_team.schemas.execution_acceptance import (
    RealDemoAcceptanceRecord,
    RealDemoAcceptanceStatus,
    RealDemoMutationApproval,
    RealDemoReadinessRecord,
)
from ai_trading_team.storage.execution_acceptance import (
    InMemoryRealDemoAcceptanceRepository,
    SQLiteRealDemoAcceptanceRepository,
)


def _coordinator() -> tuple[Any, ...]:
    service, candidate, acceptance, policy, execution_repository, adapter = execution_bundle()
    acceptance_repository = InMemoryRealDemoAcceptanceRepository()
    clock = IncrementingClock(EXECUTION_AT)
    coordinator = RealDemoAcceptanceCoordinator(
        source=service._source,
        adapter=adapter,
        execution_repository=execution_repository,
        acceptance_repository=acceptance_repository,
        execution_service=service,
        clock=clock,
    )
    return (
        coordinator,
        candidate,
        acceptance,
        policy,
        execution_repository,
        acceptance_repository,
        adapter,
        clock,
    )


def _readiness(bundle: tuple[Any, ...]) -> RealDemoReadinessRecord:
    coordinator, candidate, acceptance, policy, *_ = bundle
    return cast(
        RealDemoReadinessRecord,
        coordinator.readiness_only(
        candidate,
        acceptance,
        policy,
        acceptance_run_id="real-demo-run-m11-a",
        readiness_generation_id="real-demo-readiness-m11-a",
            ttl_seconds=60,
        ),
    )


def _approval(
    readiness: RealDemoReadinessRecord,
    *,
    control_event: ExecutionControlEvent | None = None,
) -> RealDemoMutationApproval:
    event_id = (
        readiness.execution_control_event_id
        if control_event is None
        else control_event.event_id
    )
    event_digest = (
        readiness.execution_control_event_digest
        if control_event is None
        else content_digest(control_event)
    )
    approved = readiness.readiness_created_at + timedelta(milliseconds=100)
    return RealDemoMutationApproval(
        mutation_approval_id="real-demo-mutation-approval-m11-a",
        reviewer_ref="operator-reviewer-m11",
        approved_at=approved,
        effective_from=approved,
        expires_at=readiness.readiness_expires_at,
        acceptance_run_id=readiness.acceptance_run_id,
        readiness_generation_id=readiness.readiness_generation_id,
        readiness_digest=readiness.readiness_digest,
        readiness_created_at=readiness.readiness_created_at,
        readiness_expires_at=readiness.readiness_expires_at,
        candidate_id=readiness.candidate_id,
        candidate_digest=readiness.candidate_digest,
        candidate_generation_id=readiness.candidate_generation_id,
        candidate_generation_digest=readiness.candidate_generation_digest,
        account_ref=readiness.account_ref,
        environment_ref=readiness.environment_ref,
        environment_acceptance_id=readiness.environment_acceptance_id,
        environment_acceptance_digest=readiness.environment_acceptance_digest,
        policy_ref=readiness.policy_ref,
        policy_version=readiness.policy_version,
        policy_digest=readiness.policy_digest,
        execution_control_event_id=event_id,
        execution_control_event_digest=event_digest,
        execution_control_state=ExecutionControlState.ENABLED,
        submission_limit=1,
    )


def test_readiness_only_does_not_claim_check_submit_or_consume_candidate() -> None:
    bundle = _coordinator()
    coordinator, candidate, _, _, execution_repository, acceptance_repository, adapter, _ = (
        bundle
    )

    readiness = _readiness(bundle)

    assert readiness.single_use
    assert readiness.readiness_created_at < readiness.readiness_expires_at
    assert adapter.check_calls == 0
    assert adapter.submit_calls == 0
    assert adapter.reconcile_calls == 0
    assert execution_repository.get_by_source_digest(
        content_digest(candidate.decision.shadow_record.shadow_trade_intent)
    ) is None
    assert not acceptance_repository.is_consumed(readiness.readiness_generation_id)


def test_readiness_expires_and_cannot_be_reused() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, repository, adapter, clock = bundle
    readiness = _readiness(bundle)
    approval = _approval(readiness)
    clock.current = readiness.readiness_expires_at

    with pytest.raises(ValueError, match="expired"):
        coordinator.execute_once(
            candidate,
            acceptance,
            policy,
            readiness,
            approval,
            claim_owner="operator-m11",
        )
    assert adapter.submit_calls == 0
    assert not repository.is_consumed(readiness.readiness_generation_id)


def test_execute_once_consumes_readiness_and_caps_submission_at_one() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, repository, adapter, _ = bundle
    readiness = _readiness(bundle)
    approval = _approval(readiness)

    result = coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        approval,
        claim_owner="operator-m11",
    )

    assert result.status is RealDemoAcceptanceStatus.REAL_DEMO_ACCEPTED
    assert result.submission_count == 1
    assert repository.is_consumed(readiness.readiness_generation_id)
    assert adapter.submit_calls == 1
    with pytest.raises(ValueError, match="already consumed"):
        coordinator.execute_once(
            candidate,
            acceptance,
            policy,
            readiness,
            approval,
            claim_owner="operator-m11-second",
        )
    assert adapter.submit_calls == 1


def test_approval_cannot_cross_execution_control_generation() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, execution_repository, _, adapter, _ = bundle
    readiness = _readiness(bundle)
    prior = execution_repository.current_control_event()
    assert prior is not None
    pause = ExecutionControlEvent(
        event_id="post-readiness-pause-m11",
        previous_state=ExecutionControlState.ENABLED,
        state=ExecutionControlState.PAUSED,
        operator_ref="operator-reviewer-m11",
        occurred_at=readiness.readiness_created_at + timedelta(milliseconds=210),
        reason="invalidate old readiness control generation",
    )
    enabled = ExecutionControlEvent(
        event_id="post-readiness-reenable-m11",
        previous_state=ExecutionControlState.PAUSED,
        state=ExecutionControlState.ENABLED,
        operator_ref="operator-reviewer-m11",
        occurred_at=readiness.readiness_created_at + timedelta(milliseconds=220),
        reason="new explicitly reviewed control generation",
    )
    execution_repository.append_control_event(pause)
    execution_repository.append_control_event(enabled)

    with pytest.raises(ValueError, match="exact readiness generation"):
        coordinator.execute_once(
            candidate,
            acceptance,
            policy,
            readiness,
            _approval(readiness),
            claim_owner="operator-m11",
        )
    assert adapter.submit_calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"acceptance_run_id": "different-readiness-run-m11"},
        {"candidate_id": "different-candidate-m11"},
        {"policy_digest": "sha256:" + "a" * 64},
        {"account_ref": "acct-v1:" + "a" * 64},
        {"environment_ref": "env-v1:" + "a" * 64},
    ],
)
def test_approval_cannot_cross_readiness_candidate_policy_or_environment(
    changes: dict[str, object],
) -> None:
    bundle = _coordinator()
    coordinator, _, _, _, execution_repository, acceptance_repository, adapter, clock = bundle
    readiness = _readiness(bundle)
    approval = _approval(readiness).model_copy(update=changes)
    control = execution_repository.current_control_event()
    assert control is not None

    with pytest.raises(ValueError, match="exact readiness generation"):
        acceptance_repository.consume(
            readiness,
            approval,
            control,
            consumed_at=clock(),
        )
    assert adapter.submit_calls == 0
    assert not acceptance_repository.is_consumed(readiness.readiness_generation_id)


def test_sqlite_readiness_consumption_survives_restart(tmp_path: Path) -> None:
    bundle = _coordinator()
    _, _, _, _, execution_repository, _, _, clock = bundle
    readiness = _readiness(bundle)
    approval = _approval(readiness)
    control = execution_repository.current_control_event()
    assert control is not None
    path = tmp_path / "real-demo-acceptance.sqlite3"
    first = SQLiteRealDemoAcceptanceRepository(path)
    first.add_readiness(readiness)
    first.consume(readiness, approval, control, consumed_at=clock())
    first.close()

    reopened = SQLiteRealDemoAcceptanceRepository(path)
    try:
        assert reopened.is_consumed(readiness.readiness_generation_id)
        with pytest.raises(ValueError, match="already consumed"):
            reopened.consume(readiness, approval, control, consumed_at=clock())
    finally:
        reopened.close()


def test_vendor_boundary_records_exact_binary_float_value() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, _, _, _ = bundle
    readiness = _readiness(bundle)
    result = coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        _approval(readiness),
        claim_owner="operator-m11",
    )

    audit = result.vendor_boundary_audit
    assert audit is not None
    value = audit.reference_price
    assert value.decimal_from_float == Decimal.from_float(float(value.source_decimal))
    assert value.decimal_from_string == Decimal(str(float(value.source_decimal)))
    assert value.conversion_difference == value.decimal_from_float - value.source_decimal
    assert value.float_hex == float(value.source_decimal).hex()


def test_vendor_boundary_rejects_off_grid_value_before_dispatch() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, _, adapter, _ = bundle
    readiness = _readiness(bundle)
    result = coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        _approval(readiness),
        claim_owner="operator-m11",
    )
    intent = result.execution_record.intent
    tick_size = adapter.final_observation.symbol_info.trade_tick_size
    off_grid = intent.model_copy(update={"stop_loss": intent.stop_loss + tick_size / 2})

    with pytest.raises(ValueError, match="not aligned"):
        build_vendor_boundary_audit(
            off_grid,
            adapter.final_observation.symbol_info,
            audited_at=result.sealed_at,
        )


def test_broker_success_without_confirmed_reconciliation_cannot_be_accepted() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, _, _, _ = bundle
    readiness = _readiness(bundle)
    result = coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        _approval(readiness),
        claim_owner="operator-m11",
    )
    submitted_payload = result.execution_record.model_dump(mode="python")
    submitted_payload.update(
        state=DemoExecutionState.SUBMITTED,
        reconciliation=None,
        events=result.execution_record.events[:-1],
    )
    payload = result.model_dump(mode="python")
    payload["execution_record"] = submitted_payload

    with pytest.raises(ValidationError, match="confirmed reconciled"):
        RealDemoAcceptanceRecord.model_validate(payload)


def test_confirmed_reconciliation_must_bind_exact_sealed_intent() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, _, _, _, _ = bundle
    readiness = _readiness(bundle)
    result = coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        _approval(readiness),
        claim_owner="operator-m11",
    )
    payload = result.model_dump(mode="python")
    payload["execution_record"]["reconciliation"]["intent_digest"] = "sha256:" + "a" * 64

    with pytest.raises(ValidationError, match="incompatible"):
        RealDemoAcceptanceRecord.model_validate(payload)


def test_clean_completion_pauses_execution_control() -> None:
    bundle = _coordinator()
    coordinator, candidate, acceptance, policy, execution_repository, _, _, _ = bundle
    readiness = _readiness(bundle)
    coordinator.execute_once(
        candidate,
        acceptance,
        policy,
        readiness,
        _approval(readiness),
        claim_owner="operator-m11",
    )

    assert execution_repository.control_state() is ExecutionControlState.PAUSED
