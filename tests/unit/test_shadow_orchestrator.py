import asyncio
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot
from tests.fakes.shadow import ScriptedShadowInvoker

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.orchestration.shadow import ShadowCycleOrchestrator, ShadowCyclePolicy
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.enums import (
    AgentRole,
    CycleClaimState,
    FreshnessState,
    QuantStageSelection,
    RuntimeFailureCategory,
    ShadowDisposition,
    StageExecutionStatus,
    TradeAction,
)
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import AccountRiskContext
from ai_trading_team.schemas.shadow import ShadowDecisionRecord
from ai_trading_team.storage.shadow_audit import (
    DuplicateCycleError,
    InMemoryShadowAuditRepository,
    SQLiteShadowAuditRepository,
)


def run_cycle(
    invoker: ScriptedShadowInvoker,
    *,
    context: AccountRiskContext | None = None,
    snapshot: MarketSnapshot | None = None,
    policy: ShadowCyclePolicy | None = None,
    repository: InMemoryShadowAuditRepository | SQLiteShadowAuditRepository | None = None,
) -> ShadowDecisionRecord:
    active_snapshot = snapshot or risk_snapshot()
    active_context = context or account_context(active_snapshot)
    active_repository = repository or InMemoryShadowAuditRepository()
    orchestrator = ShadowCycleOrchestrator(
        invoker=invoker,
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=active_repository,
        policy=policy,
        clock=lambda: EVALUATED_AT + timedelta(seconds=30),
    )
    return asyncio.run(orchestrator.run_shadow_cycle(active_snapshot, active_context))


def test_full_fake_shadow_cycle_approved_is_never_executed() -> None:
    invoker = ScriptedShadowInvoker(chief_action=TradeAction.BUY)
    record = run_cycle(invoker)

    assert record.decision_cycle.final_disposition is ShadowDisposition.WOULD_BUY
    assert record.shadow_trade_intent is not None
    assert record.shadow_trade_intent.execution_status.value == "NOT_EXECUTED_SHADOW"
    assert record.shadow_trade_intent.selected_volume == Decimal("0.01")
    assert [stage.stage_number for stage in record.decision_cycle.stages] == list(range(1, 7))
    assert record.decision_cycle.stages[2].status is StageExecutionStatus.SKIPPED
    assert len(invoker.calls) == 6
    assert all(call[0] is not AgentRole.PERFORMANCE_REVIEWER for call in invoker.calls)

    audit_json = record.model_dump_json().casefold()
    assert "broker-demo" not in audit_json
    assert "12345678" not in audit_json
    assert "raw_provider_response" not in audit_json
    assert "prompt_body" not in audit_json
    assert "api_key" not in audit_json
    assert "password" not in audit_json


def test_chief_hold_is_success_and_skips_risk() -> None:
    record = run_cycle(ScriptedShadowInvoker())

    assert record.decision_cycle.final_disposition is ShadowDisposition.CHIEF_HOLD
    assert record.decision_cycle.risk_decision is None
    assert record.shadow_trade_intent is None
    assert record.decision_cycle.stages[5].status is StageExecutionStatus.SKIPPED


def test_m3_rejection_is_authoritative_and_creates_no_intent() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot, open_position_count=1)
    record = run_cycle(
        ScriptedShadowInvoker(chief_action=TradeAction.BUY),
        snapshot=snapshot,
        context=context,
    )

    assert record.decision_cycle.final_disposition is ShadowDisposition.RISK_REJECTED
    assert record.shadow_trade_intent is None


def test_m3_halted_state_is_authoritative_and_creates_no_intent() -> None:
    snapshot = risk_snapshot(equity=Decimal("40"))
    context = account_context(
        snapshot,
        peak_equity=Decimal("50"),
        day_start_equity=Decimal("50"),
    )
    record = run_cycle(
        ScriptedShadowInvoker(chief_action=TradeAction.BUY),
        snapshot=snapshot,
        context=context,
    )

    assert record.decision_cycle.final_disposition is ShadowDisposition.RISK_HALTED
    assert record.shadow_trade_intent is None


def test_preflight_account_context_mismatch_aborts_before_agent_dispatch() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot).model_copy(update={"account_ref": "acct-v1:" + "0" * 64})
    invoker = ScriptedShadowInvoker()

    record = run_cycle(invoker, context=context)

    assert record.decision_cycle.final_disposition is ShadowDisposition.ABORTED
    assert invoker.calls == []


def test_one_stage_one_unavailable_continues_with_degraded_quorum() -> None:
    invoker = ScriptedShadowInvoker(
        failures={AgentRole.MARKET_CONTEXT: RuntimeFailureCategory.PROVIDER_TIMEOUT}
    )
    record = run_cycle(invoker)

    assert record.decision_cycle.final_disposition is ShadowDisposition.CHIEF_HOLD
    assert record.decision_cycle.stages[0].status is StageExecutionStatus.DEGRADED
    assert len(record.decision_cycle.agent_failures) == 1


def test_two_stage_one_failures_produce_policy_hold() -> None:
    invoker = ScriptedShadowInvoker(
        failures={
            AgentRole.MARKET_CONTEXT: RuntimeFailureCategory.PROVIDER_TIMEOUT,
            AgentRole.TREND_ANALYST: RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
        }
    )
    record = run_cycle(invoker)

    assert record.decision_cycle.final_disposition is ShadowDisposition.POLICY_HOLD
    assert len(invoker.calls) == 3


def test_required_downstream_invalid_output_produces_policy_hold() -> None:
    invoker = ScriptedShadowInvoker(
        failures={AgentRole.ENTRY_ANALYST: RuntimeFailureCategory.INVALID_MODEL_OUTPUT}
    )
    record = run_cycle(invoker)

    assert record.decision_cycle.final_disposition is ShadowDisposition.POLICY_HOLD
    assert len(invoker.calls) == 4


def test_budget_exhaustion_for_required_agent_produces_policy_hold() -> None:
    invoker = ScriptedShadowInvoker(
        failures={AgentRole.ENTRY_ANALYST: RuntimeFailureCategory.BUDGET_EXCEEDED}
    )
    record = run_cycle(invoker)

    assert record.decision_cycle.final_disposition is ShadowDisposition.POLICY_HOLD
    assert record.decision_cycle.risk_decision is None


def test_only_stage_one_runs_concurrently() -> None:
    invoker = ScriptedShadowInvoker(delay_seconds=0.01)
    run_cycle(invoker)

    assert invoker.max_active == 3


def test_optional_quant_roles_run_only_when_selected() -> None:
    invoker = ScriptedShadowInvoker()
    record = run_cycle(
        invoker,
        policy=ShadowCyclePolicy(
            quant_stage_selection=QuantStageSelection.QUANT_AND_SENIOR_REVIEW
        ),
    )

    roles = [call[0] for call in invoker.calls]
    assert AgentRole.QUANT_RESEARCHER in roles
    assert AgentRole.SENIOR_QUANT_DEVELOPER in roles
    assert record.decision_cycle.stages[2].status is StageExecutionStatus.COMPLETED


def test_debate_rounds_are_bounded_and_invocation_ids_are_unique() -> None:
    invoker = ScriptedShadowInvoker(chief_action=TradeAction.BUY)
    record = run_cycle(invoker, policy=ShadowCyclePolicy(debate_rounds=3))

    debate_calls = [
        call
        for call in invoker.calls
        if call[0] in {AgentRole.SKEPTIC, AgentRole.CHIEF_TRADER}
    ]
    assert len(debate_calls) == 6
    assert len({call[3] for call in debate_calls}) == 6
    assert [call[2] for call in debate_calls] == [1, 1, 2, 2, 3, 3]
    assert len(record.decision_cycle.chief_decisions) == 3


def test_duplicate_cycle_never_dispatches_again() -> None:
    repository = InMemoryShadowAuditRepository()
    invoker = ScriptedShadowInvoker()
    run_cycle(invoker, repository=repository)
    call_count = len(invoker.calls)

    with pytest.raises(DuplicateCycleError):
        run_cycle(invoker, repository=repository)

    assert len(invoker.calls) == call_count


def test_sqlite_retains_incomplete_claim_and_refuses_replay(tmp_path: Path) -> None:
    path = tmp_path / "shadow.sqlite3"
    repository = SQLiteShadowAuditRepository(path)
    snapshot = risk_snapshot()
    repository.claim_cycle(snapshot.cycle_id, snapshot.snapshot_id, at=EVALUATED_AT)
    repository.close()

    reopened = SQLiteShadowAuditRepository(path)
    claim = reopened.get_claim(snapshot.cycle_id)
    assert claim is not None and claim.state is CycleClaimState.INCOMPLETE
    with pytest.raises(DuplicateCycleError):
        reopened.claim_cycle(snapshot.cycle_id, snapshot.snapshot_id, at=EVALUATED_AT)
    reopened.close()


def test_explicit_abandonment_remains_auditable_and_cannot_be_reused() -> None:
    repository = InMemoryShadowAuditRepository()
    snapshot = risk_snapshot()
    repository.claim_cycle(snapshot.cycle_id, snapshot.snapshot_id, at=EVALUATED_AT)
    abandoned = repository.abandon(
        snapshot.cycle_id,
        at=EVALUATED_AT + timedelta(seconds=1),
        reason="process terminated before finalization",
    )

    assert abandoned.state is CycleClaimState.ABANDONED
    with pytest.raises(DuplicateCycleError):
        repository.claim_cycle(snapshot.cycle_id, snapshot.snapshot_id, at=EVALUATED_AT)


def test_sqlite_round_trip_preserves_decimal_values(tmp_path: Path) -> None:
    repository = SQLiteShadowAuditRepository(tmp_path / "shadow.sqlite3")
    record = run_cycle(
        ScriptedShadowInvoker(chief_action=TradeAction.BUY), repository=repository
    )

    restored = repository.get_record(record.decision_cycle.cycle_id)
    assert restored is not None and restored.shadow_trade_intent is not None
    assert isinstance(restored.shadow_trade_intent.selected_volume, Decimal)
    assert restored == record
    repository.close()


def test_stale_but_valid_snapshot_holds_without_agent_dispatch() -> None:
    snapshot = risk_snapshot()
    original = snapshot.consistency.freshness
    stale_tick = original.tick.model_copy(
        update={
            "observed_at": original.tick.evaluated_at - timedelta(hours=1),
            "age": timedelta(hours=1),
            "maximum_age": timedelta(seconds=1),
            "state": FreshnessState.STALE,
        }
    )
    freshness = original.model_copy(
        update={"tick": stale_tick, "overall": FreshnessState.STALE}
    )
    stale = snapshot.model_copy(
        update={
            "consistency": snapshot.consistency.model_copy(update={"freshness": freshness})
        }
    )
    invoker = ScriptedShadowInvoker()
    repository = InMemoryShadowAuditRepository()
    orchestrator = ShadowCycleOrchestrator(
        invoker=invoker,
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=repository,
        clock=lambda: EVALUATED_AT + timedelta(seconds=30),
    )

    record = asyncio.run(orchestrator.run_shadow_cycle(stale, account_context(stale)))

    assert record.decision_cycle.final_disposition is ShadowDisposition.POLICY_HOLD
    assert invoker.calls == []


def test_identical_inputs_and_fixed_clock_produce_byte_identical_records() -> None:
    first = run_cycle(ScriptedShadowInvoker(chief_action=TradeAction.BUY))
    second = run_cycle(ScriptedShadowInvoker(chief_action=TradeAction.BUY))
    assert first.model_dump_json() == second.model_dump_json()
