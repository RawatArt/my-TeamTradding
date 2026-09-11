import asyncio
import json
from decimal import Decimal

from tests.fakes.runtime import (
    FakeProviderAdapter,
    MonotonicClock,
    SequenceClock,
    budget_policy,
    capability_profile,
    invocation_request,
    pricing_profile,
    prompt_registry,
    provider_response,
    retry_policy,
    runtime_profile,
    semantic_body,
)

from ai_trading_team.runtime.budget import BudgetGuard, InMemoryBudgetLedger
from ai_trading_team.runtime.errors import ProviderError
from ai_trading_team.runtime.router import RuntimeRouter
from ai_trading_team.schemas.agents import MarketContextOutput
from ai_trading_team.schemas.enums import (
    AgentOutputStatus,
    BudgetReservationState,
    ModelProvider,
    RuntimeFailureCategory,
)
from ai_trading_team.schemas.runtime import AgentInvocationResult


def invoke(
    adapter: FakeProviderAdapter,
    *,
    ledger: InMemoryBudgetLedger | None = None,
    capability_overrides: dict[str, object] | None = None,
    max_attempts: int = 3,
    retry_rate_limits: bool = False,
) -> tuple[AgentInvocationResult, InMemoryBudgetLedger]:
    active_ledger = ledger or InMemoryBudgetLedger()
    router = RuntimeRouter(
        prompts=prompt_registry(),
        providers={ModelProvider.FAKE: adapter},
        budget=BudgetGuard(active_ledger),
        clock=SequenceClock(),
        monotonic_clock=MonotonicClock(),
    )
    capability = capability_profile()
    if capability_overrides:
        capability = capability.model_copy(update=capability_overrides)
    result = asyncio.run(
        router.invoke(
            invocation_request(),
            runtime=runtime_profile(),
            retry_policy=retry_policy(max_attempts=max_attempts).model_copy(
                update={"retry_rate_limits": retry_rate_limits}
            ),
            capability=capability,
            budget_policy=budget_policy(),
            pricing=pricing_profile(),
        )
    )
    return result, active_ledger


def test_fake_provider_end_to_end_produces_trusted_typed_output() -> None:
    adapter = FakeProviderAdapter()
    result, ledger = invoke(adapter)

    assert result.failure is None
    assert isinstance(result.output, MarketContextOutput)
    assert result.output.status is AgentOutputStatus.SUCCESS
    assert isinstance(result.output.confidence, Decimal)
    assert result.trace.invocation_id == "invocation-m5-001"
    assert result.trace.attempts == 1
    assert result.telemetry.reservation_state is BudgetReservationState.SETTLED
    assert ledger.get(result.trace.invocation_id).state is BudgetReservationState.SETTLED  # type: ignore[union-attr]
    dispatched_schema = json.loads(adapter.requests[0].output_json_schema)
    assert "status" not in dispatched_schema["properties"]


def test_runtime_derives_degraded_status_from_validated_semantic_warnings() -> None:
    adapter = FakeProviderAdapter([provider_response(semantic_body(with_warning=True))])
    result, _ = invoke(adapter)

    assert isinstance(result.output, MarketContextOutput)
    assert result.output.status is AgentOutputStatus.DEGRADED
    assert len(result.output.warnings) == 1


def test_model_cannot_self_declare_success() -> None:
    payload = json.loads(semantic_body())
    payload["status"] = "SUCCESS"
    adapter = FakeProviderAdapter([provider_response(json.dumps(payload))])
    result, _ = invoke(adapter)

    assert result.output is None
    assert result.runtime_failure_category is RuntimeFailureCategory.INVALID_MODEL_OUTPUT
    assert result.failure is not None
    assert adapter.invoke_count == 1


def test_retryable_provider_failure_never_exceeds_max_attempts() -> None:
    transient = ProviderError(
        RuntimeFailureCategory.PROVIDER_TRANSIENT,
        "sanitized transient error",
        retryable=True,
        dispatch_occurred=True,
    )
    adapter = FakeProviderAdapter([transient, transient, transient, provider_response()])
    result, ledger = invoke(adapter, max_attempts=3)

    assert result.output is None
    assert result.trace.attempts == 3
    assert adapter.invoke_count == 3
    assert result.telemetry.reservation_state is BudgetReservationState.UNCERTAIN
    assert ledger.get(result.trace.invocation_id).state is BudgetReservationState.UNCERTAIN  # type: ignore[union-attr]
    attempts = ledger.attempts(result.trace.invocation_id)
    assert [item.attempt_number for item in attempts] == [1, 2, 3]
    assert all(item.state is BudgetReservationState.UNCERTAIN for item in attempts)


def test_retry_attempt_keeps_logical_identity_and_has_its_own_reservation() -> None:
    transient = ProviderError(
        RuntimeFailureCategory.PROVIDER_TRANSIENT,
        "sanitized transient error",
        retryable=True,
        dispatch_occurred=True,
    )
    adapter = FakeProviderAdapter([transient, provider_response()])
    result, ledger = invoke(adapter, max_attempts=2)

    assert result.output is not None
    assert {request.invocation_id for request in adapter.requests} == {result.trace.invocation_id}
    assert [request.attempt for request in adapter.requests] == [1, 2]
    reservations = ledger.attempts(result.trace.invocation_id)
    assert [item.state for item in reservations] == [
        BudgetReservationState.UNCERTAIN,
        BudgetReservationState.SETTLED,
    ]


def test_nonretryable_provider_failure_calls_provider_once() -> None:
    failure = ProviderError(
        RuntimeFailureCategory.PROVIDER_AUTHENTICATION,
        "provider authentication failed",
        retryable=False,
        dispatch_occurred=True,
    )
    adapter = FakeProviderAdapter([failure])
    result, _ = invoke(adapter)

    assert result.output is None
    assert adapter.invoke_count == 1
    assert result.trace.attempts == 1


def test_definitely_undispatched_provider_failure_releases_only_that_attempt() -> None:
    failure = ProviderError(
        RuntimeFailureCategory.PROVIDER_AUTHENTICATION,
        "provider rejected request before dispatch",
        retryable=False,
        dispatch_occurred=False,
    )
    adapter = FakeProviderAdapter([failure])
    result, ledger = invoke(adapter)

    assert result.output is None
    assert result.telemetry.reservation_state is BudgetReservationState.RELEASED
    reservation = ledger.get(result.trace.invocation_id)
    assert reservation is not None
    assert reservation.state is BudgetReservationState.RELEASED


def test_rate_limit_is_not_retried_when_policy_disallows_it() -> None:
    failure = ProviderError(
        RuntimeFailureCategory.PROVIDER_RATE_LIMIT,
        "provider rate limit",
        retryable=True,
        dispatch_occurred=True,
    )
    adapter = FakeProviderAdapter([failure, provider_response()])
    result, _ = invoke(adapter, retry_rate_limits=False)

    assert result.output is None
    assert adapter.invoke_count == 1


def test_capability_mismatch_fails_before_dispatch_and_before_reservation() -> None:
    adapter = FakeProviderAdapter()
    result, ledger = invoke(
        adapter,
        capability_overrides={"json_schema_supported": False},
    )

    assert result.runtime_failure_category is RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE
    assert result.trace.attempts == 0
    assert adapter.invoke_count == 0
    assert ledger.get(result.trace.invocation_id) is None


def test_duplicate_invocation_never_dispatches_twice() -> None:
    ledger = InMemoryBudgetLedger()
    adapter = FakeProviderAdapter([provider_response(), provider_response()])
    first, _ = invoke(adapter, ledger=ledger)
    second, _ = invoke(adapter, ledger=ledger)

    assert first.output is not None
    assert second.runtime_failure_category is RuntimeFailureCategory.DUPLICATE_INVOCATION
    assert second.trace.attempts == 0
    assert adapter.invoke_count == 1


def test_identical_inputs_and_injected_clocks_produce_byte_identical_results() -> None:
    first, _ = invoke(FakeProviderAdapter())
    second, _ = invoke(FakeProviderAdapter())

    assert first.model_dump_json() == second.model_dump_json()
