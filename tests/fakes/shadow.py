"""Deterministic M6 fakes with no network, MT5, or execution capability."""

import asyncio
from datetime import timedelta
from decimal import Decimal

from ai_trading_team.orchestration.identifiers import (
    logical_invocation_id,
    logical_output_id,
)
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    AgentRole,
    BudgetReservationState,
    FailureDisposition,
    MetricAvailability,
    ModelProvider,
    RuntimeFailureCategory,
    TokenEstimateMethod,
    TradeAction,
)
from ai_trading_team.schemas.orchestration import AgentFailureRecord
from ai_trading_team.schemas.runtime import (
    AgentInvocationResult,
    BudgetReservation,
    InvocationTelemetry,
    InvocationTrace,
    InvocationUsage,
    TokenEstimate,
    UsageValue,
)
from tests.fakes.agents import (
    chief_output,
    entry_output,
    market_context_output,
    price_action_output,
    quant_developer_output,
    quant_output,
    skeptic_output,
    trend_output,
)
from tests.fakes.risk import EVALUATED_AT


def _reported(value: int) -> UsageValue:
    return UsageValue(value=value, availability=MetricAvailability.REPORTED)


class ScriptedShadowInvoker:
    """Return typed role outputs while exposing concurrency and call history."""

    def __init__(
        self,
        *,
        chief_action: TradeAction | None = None,
        failures: dict[AgentRole, RuntimeFailureCategory] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.chief_action = chief_action or TradeAction.HOLD
        self.failures = failures or {}
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[AgentRole, int, int | None, str]] = []
        self.active = 0
        self.max_active = 0

    async def invoke(
        self,
        role: AgentRole,
        context: CoreModel,
        *,
        stage_number: int,
        debate_round: int | None = None,
    ) -> AgentInvocationResult:
        cycle_id = str(context.model_dump()["cycle_id"])
        snapshot_id = str(context.model_dump()["snapshot_id"])
        invocation_id = logical_invocation_id(
            cycle_id, snapshot_id, stage_number, role, debate_round
        )
        output_id = logical_output_id(invocation_id)
        self.calls.append((role, stage_number, debate_round, invocation_id))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
        finally:
            self.active -= 1

        at = EVALUATED_AT + timedelta(seconds=len(self.calls))
        reservation = BudgetReservation(
            invocation_id=invocation_id,
            cycle_id=cycle_id,
            state=BudgetReservationState.SETTLED,
            policy_ref="budget-shadow-test",
            reserved_amount=Decimal("0.01"),
            settled_amount=Decimal("0.001"),
            currency="USD",
            created_at=at,
            updated_at=at,
        )
        telemetry = InvocationTelemetry(
            usage=InvocationUsage(
                input_tokens=_reported(10),
                output_tokens=_reported(10),
            ),
            input_estimate=TokenEstimate(
                tokens=10,
                method=TokenEstimateMethod.CONSERVATIVE_ESTIMATE,
                conservative=True,
                estimated_at=at,
            ),
            attempt_count=1,
            retry_count=0,
            latency_milliseconds=Decimal("1"),
            estimated_cost=Decimal("0.001"),
            estimated_cost_availability=MetricAvailability.REPORTED,
            currency="USD",
            reservation_state=BudgetReservationState.SETTLED,
            attempt_reservations=(reservation,),
        )
        trace = InvocationTrace(
            invocation_id=invocation_id,
            output_id=output_id,
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            agent_role=role,
            agent_version="1.0.0",
            prompt_id="test-prompt",
            prompt_version="1.0.0",
            prompt_digest="sha256:" + "0" * 64,
            runtime_profile_ref="runtime-fake-v1",
            provider=ModelProvider.FAKE,
            model_identifier="fake-structured-model",
            request_started_at=at,
            request_completed_at=at,
            attempts=1,
        )
        failure_category = self.failures.get(role)
        if failure_category is not None:
            agent_category = (
                AgentFailureCategory.TIMEOUT
                if failure_category is RuntimeFailureCategory.PROVIDER_TIMEOUT
                else AgentFailureCategory.INVALID_OUTPUT
                if failure_category is RuntimeFailureCategory.INVALID_MODEL_OUTPUT
                else AgentFailureCategory.UNAVAILABLE_AGENT
            )
            failure = AgentFailureRecord(
                failure_id=f"failure-{invocation_id[-16:]}",
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                agent_role=role,
                category=agent_category,
                occurred_at=at,
                sanitized_detail="scripted provider failure",
                disposition=FailureDisposition.HOLD,
            )
            return AgentInvocationResult(
                trace=trace,
                failure=failure,
                runtime_failure_category=failure_category,
                telemetry=telemetry,
            )

        output = self._output(role).model_copy(
            update={
                "output_id": output_id,
                "cycle_id": cycle_id,
                "snapshot_id": snapshot_id,
                "produced_at": at,
            }
        )
        return AgentInvocationResult(trace=trace, output=output, telemetry=telemetry)

    def _output(self, role: AgentRole) -> CoreModel:
        if role is AgentRole.MARKET_CONTEXT:
            return market_context_output()
        if role is AgentRole.TREND_ANALYST:
            return trend_output()
        if role is AgentRole.PRICE_ACTION_ANALYST:
            return price_action_output()
        if role is AgentRole.ENTRY_ANALYST:
            return entry_output()
        if role is AgentRole.QUANT_RESEARCHER:
            return quant_output()
        if role is AgentRole.SENIOR_QUANT_DEVELOPER:
            return quant_developer_output()
        if role is AgentRole.SKEPTIC:
            return skeptic_output()
        if role is AgentRole.CHIEF_TRADER:
            return chief_output(self.chief_action)
        raise KeyError(role)
