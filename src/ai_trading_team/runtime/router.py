"""Auditable single-agent runtime router with strict preflight and bounded attempts."""

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic

from pydantic import ValidationError

from ai_trading_team.orchestration.failures import AgentFailurePolicy
from ai_trading_team.prompts.registry import PromptRegistry, PromptRegistryError
from ai_trading_team.runtime.budget import BudgetGuard, estimate_reported_cost
from ai_trading_team.runtime.contracts import canonical_schema_json, contract_for_role
from ai_trading_team.runtime.errors import ProviderError, RuntimeInvocationError
from ai_trading_team.runtime.protocols import ModelProviderAdapter
from ai_trading_team.runtime.validation import parse_model_body, validate_compatibility
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    AgentOutputStatus,
    BudgetReservationState,
    MetricAvailability,
    ModelProvider,
    RuntimeFailureCategory,
    TokenEstimateMethod,
)
from ai_trading_team.schemas.orchestration import AgentFailureRecord
from ai_trading_team.schemas.runtime import (
    AgentInvocationRequest,
    AgentInvocationResult,
    AIBudgetPolicy,
    BudgetReservation,
    InvocationTelemetry,
    InvocationTrace,
    InvocationUsage,
    ModelCapabilityProfile,
    PricingProfile,
    ProviderRequest,
    ProviderResponse,
    RetryPolicy,
    RuntimeProfile,
    TokenEstimate,
)


class RuntimeRouter:
    """Invoke exactly one role through one selected provider; never orchestrate agents."""

    def __init__(
        self,
        *,
        prompts: PromptRegistry,
        providers: Mapping[ModelProvider, ModelProviderAdapter],
        budget: BudgetGuard,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._prompts = prompts
        self._providers = dict(providers)
        self._budget = budget
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic_clock or monotonic

    async def invoke(
        self,
        request: AgentInvocationRequest,
        *,
        runtime: RuntimeProfile,
        capability: ModelCapabilityProfile,
        retry_policy: RetryPolicy,
        budget_policy: AIBudgetPolicy,
        pricing: PricingProfile,
    ) -> AgentInvocationResult:
        """Run one bounded typed invocation and always return output or a sanitized failure."""
        started_at = self._utc_now()
        started_monotonic = self._monotonic()
        attempts = 0
        estimate = self._unavailable_estimate(started_at)
        reservation_state: BudgetReservationState | None = None
        provider_response: ProviderResponse | None = None
        attempt_reservations: list[BudgetReservation] = []

        try:
            contract = contract_for_role(request.descriptor.role)
            if runtime.retry_policy_ref != retry_policy.policy_ref:
                raise RuntimeInvocationError(
                    RuntimeFailureCategory.INVALID_REQUEST,
                    "runtime retry policy reference does not match supplied policy",
                )
            prompt = self._prompts.get(
                request.descriptor.prompt_ref.prompt_id,
                request.descriptor.prompt_ref.prompt_version,
            )
            adapter = self._providers.get(runtime.provider)
            if adapter is None or adapter.provider is not runtime.provider:
                raise RuntimeInvocationError(
                    RuntimeFailureCategory.PROVIDER_UNAVAILABLE,
                    "configured provider adapter is unavailable",
                )
            provider_request = ProviderRequest(
                invocation_id=request.invocation_id,
                provider=runtime.provider,
                model_identifier=runtime.model_identifier,
                attempt=1,
                system_prompt=prompt.content,
                context_json=request.context.model_dump_json(),
                output_json_schema=canonical_schema_json(
                    contract.body_adapter.json_schema(mode="validation")
                ),
                max_output_tokens=runtime.max_output_tokens,
                timeout_seconds=runtime.request_timeout_seconds,
                reasoning_effort=runtime.reasoning_effort,
            )
            adapter.prepare()
            estimate = await adapter.estimate_input_tokens(provider_request)
            validate_compatibility(
                request,
                prompt,
                runtime,
                capability,
                contract,
                estimate,
            )
            last_error: ProviderError | None = None
            for attempt in range(1, retry_policy.max_attempts + 1):
                attempt_request = provider_request.model_copy(update={"attempt": attempt})
                remaining = runtime.total_timeout_seconds - (
                    self._monotonic() - started_monotonic
                )
                if remaining <= 0:
                    last_error = ProviderError(
                        RuntimeFailureCategory.PROVIDER_TIMEOUT,
                        "total invocation timeout exceeded",
                        retryable=False,
                        dispatch_occurred=False,
                    )
                    break
                reservation = self._budget.reserve(
                    invocation_id=request.invocation_id,
                    cycle_id=request.cycle_id,
                    runtime=runtime,
                    capability_input_estimate=estimate,
                    policy=budget_policy,
                    pricing=pricing,
                    at=self._utc_now(),
                    attempt_number=attempt,
                )
                attempts = attempt
                attempt_reservations.append(reservation)
                reservation = self._budget.mark_dispatched(
                    request.invocation_id,
                    attempt_number=attempt,
                    at=self._utc_now(),
                )
                attempt_reservations[-1] = reservation
                reservation_state = reservation.state
                try:
                    provider_response = await asyncio.wait_for(
                        adapter.invoke(attempt_request),
                        timeout=min(float(runtime.request_timeout_seconds), remaining),
                    )
                    last_error = None
                    break
                except TimeoutError:
                    last_error = ProviderError(
                        RuntimeFailureCategory.PROVIDER_TIMEOUT,
                        "provider request timed out",
                        retryable=True,
                        dispatch_occurred=True,
                    )
                except ProviderError as exc:
                    last_error = exc
                except Exception as exc:
                    last_error = ProviderError(
                        RuntimeFailureCategory.UNKNOWN_PROVIDER_ERROR,
                        "provider adapter failed unexpectedly",
                        retryable=False,
                        dispatch_occurred=True,
                    )
                    last_error.__cause__ = exc
                if last_error.dispatch_occurred:
                    reservation = self._budget.mark_uncertain(
                        request.invocation_id,
                        attempt_number=attempt,
                        at=self._utc_now(),
                    )
                else:
                    reservation = self._budget.release_undispatched_attempt(
                        request.invocation_id,
                        attempt_number=attempt,
                        at=self._utc_now(),
                    )
                attempt_reservations[-1] = reservation
                reservation_state = reservation.state
                if not self._retry_allowed(last_error, retry_policy) or (
                    attempt >= retry_policy.max_attempts
                ):
                    break
                await asyncio.sleep(0)

            if provider_response is None:
                assert last_error is not None
                raise last_error

            settled_cost = self._reported_cost(provider_response.usage, pricing)
            if settled_cost is None:
                reservation = self._budget.mark_uncertain(
                    request.invocation_id,
                    attempt_number=attempts,
                    at=self._utc_now(),
                )
            else:
                reservation = self._budget.settle(
                    request.invocation_id,
                    settled_cost,
                    attempt_number=attempts,
                    at=self._utc_now(),
                )
            reservation_state = reservation.state
            attempt_reservations[-1] = reservation

            body = parse_model_body(provider_response.response_json, contract)
            status = AgentOutputStatus.DEGRADED if body.warnings else AgentOutputStatus.SUCCESS
            try:
                output = contract.output_type.model_validate(
                    {
                        "output_id": request.output_id,
                        "cycle_id": request.cycle_id,
                        "snapshot_id": request.snapshot_id,
                        "agent_name": request.descriptor.agent_name,
                        "agent_role": request.descriptor.role,
                        "agent_version": request.descriptor.agent_version,
                        "prompt_ref": request.descriptor.prompt_ref,
                        "runtime_profile_ref": request.descriptor.runtime_profile_ref,
                        "invocation_policy_ref": request.descriptor.invocation_policy_ref,
                        "cost_policy_ref": request.descriptor.cost_policy_ref,
                        "produced_at": provider_response.responded_at,
                        "status": status,
                        **body.model_dump(mode="python"),
                    },
                    strict=True,
                )
            except ValidationError as exc:
                raise RuntimeInvocationError(
                    RuntimeFailureCategory.INVALID_MODEL_OUTPUT,
                    "validated body is incompatible with the trusted output envelope",
                ) from exc
            completed_at = self._utc_now()
            return AgentInvocationResult(
                trace=self._trace(
                    request,
                    prompt.content_digest,
                    runtime,
                    started_at,
                    completed_at,
                    attempts,
                ),
                output=output,
                telemetry=self._telemetry(
                    usage=provider_response.usage,
                    estimate=estimate,
                    attempts=attempts,
                    started_monotonic=started_monotonic,
                    pricing=pricing,
                    attempt_reservations=tuple(attempt_reservations),
                    provider_request_id=provider_response.provider_request_id,
                    reservation_state=reservation_state,
                ),
            )
        except PromptRegistryError as exc:
            runtime_error = RuntimeInvocationError(
                RuntimeFailureCategory.INVALID_PROMPT_REFERENCE,
                "prompt artifact could not be resolved",
            )
            runtime_error.__cause__ = exc
        except RuntimeInvocationError as exc:
            runtime_error = exc

        completed_at = self._utc_now()
        return AgentInvocationResult(
            trace=self._trace(
                request,
                request.descriptor.prompt_ref.content_digest
                or "sha256:" + "0" * 64,
                runtime,
                started_at,
                completed_at,
                attempts,
            ),
            failure=self._failure(request, runtime_error, completed_at),
            runtime_failure_category=runtime_error.category,
            telemetry=self._telemetry(
                usage=provider_response.usage if provider_response else InvocationUsage(),
                estimate=estimate,
                attempts=attempts,
                started_monotonic=started_monotonic,
                pricing=pricing,
                attempt_reservations=tuple(attempt_reservations),
                provider_request_id=(
                    provider_response.provider_request_id if provider_response else None
                ),
                reservation_state=reservation_state,
            ),
        )

    def _trace(
        self,
        request: AgentInvocationRequest,
        prompt_digest: str,
        runtime: RuntimeProfile,
        started_at: datetime,
        completed_at: datetime,
        attempts: int,
    ) -> InvocationTrace:
        return InvocationTrace(
            invocation_id=request.invocation_id,
            output_id=request.output_id,
            cycle_id=request.cycle_id,
            snapshot_id=request.snapshot_id,
            agent_role=request.descriptor.role,
            agent_version=request.descriptor.agent_version,
            prompt_id=request.descriptor.prompt_ref.prompt_id,
            prompt_version=request.descriptor.prompt_ref.prompt_version,
            prompt_digest=prompt_digest,
            runtime_profile_ref=runtime.profile_ref,
            provider=runtime.provider,
            model_identifier=runtime.model_identifier,
            request_started_at=started_at,
            request_completed_at=completed_at,
            attempts=attempts,
        )

    def _failure(
        self,
        request: AgentInvocationRequest,
        error: RuntimeInvocationError,
        occurred_at: datetime,
    ) -> AgentFailureRecord:
        category_map = {
            RuntimeFailureCategory.PROVIDER_TIMEOUT: AgentFailureCategory.TIMEOUT,
            RuntimeFailureCategory.INVALID_MODEL_OUTPUT: AgentFailureCategory.INVALID_OUTPUT,
            RuntimeFailureCategory.SCHEMA_INCOMPATIBLE: AgentFailureCategory.SCHEMA_MISMATCH,
            RuntimeFailureCategory.CAPABILITY_INCOMPATIBLE: AgentFailureCategory.SCHEMA_MISMATCH,
            RuntimeFailureCategory.PROVIDER_UNAVAILABLE: AgentFailureCategory.UNAVAILABLE_AGENT,
        }
        category = category_map.get(error.category, AgentFailureCategory.UNKNOWN)
        disposition = AgentFailurePolicy.resolve(category, role=request.descriptor.role)
        digest = hashlib.sha256(request.invocation_id.encode("utf-8")).hexdigest()[:16]
        return AgentFailureRecord(
            failure_id=f"failure-{digest}",
            cycle_id=request.cycle_id,
            snapshot_id=request.snapshot_id,
            agent_role=request.descriptor.role,
            execution_profile=request.descriptor.execution_profile,
            category=category,
            occurred_at=occurred_at,
            sanitized_detail=error.detail,
            disposition=disposition,
        )

    def _telemetry(
        self,
        *,
        usage: InvocationUsage,
        estimate: TokenEstimate,
        attempts: int,
        started_monotonic: float,
        pricing: PricingProfile,
        attempt_reservations: tuple[BudgetReservation, ...],
        provider_request_id: str | None,
        reservation_state: BudgetReservationState | None,
    ) -> InvocationTelemetry:
        reported_cost = self._reported_cost(usage, pricing)
        reserved_amount = sum(
            (
                item.settled_amount
                if item.state is BudgetReservationState.SETTLED
                and item.settled_amount is not None
                else item.reserved_amount
                if item.state is not BudgetReservationState.RELEASED
                else Decimal("0")
                for item in attempt_reservations
            ),
            start=Decimal("0"),
        )
        prior_attempts_are_released = all(
            item.state is BudgetReservationState.RELEASED
            for item in attempt_reservations[:-1]
        )
        exact_reported = reported_cost is not None and prior_attempts_are_released
        cost = reported_cost if exact_reported else (
            reserved_amount if attempt_reservations else None
        )
        availability = (
            MetricAvailability.REPORTED
            if exact_reported
            else MetricAvailability.ESTIMATED
            if attempt_reservations
            else MetricAvailability.UNAVAILABLE
        )
        return InvocationTelemetry(
            usage=usage,
            input_estimate=estimate,
            attempt_count=attempts,
            retry_count=max(attempts - 1, 0),
            latency_milliseconds=Decimal(str((self._monotonic() - started_monotonic) * 1000)),
            estimated_cost=cost,
            estimated_cost_availability=availability,
            currency=pricing.currency,
            provider_request_id=provider_request_id,
            reservation_state=reservation_state,
            attempt_reservations=attempt_reservations,
        )

    @staticmethod
    def _reported_cost(usage: InvocationUsage, pricing: PricingProfile) -> Decimal | None:
        if usage.input_tokens.value is None or usage.output_tokens.value is None:
            return None
        return estimate_reported_cost(
            usage.input_tokens.value,
            usage.output_tokens.value,
            pricing,
        )

    @staticmethod
    def _retry_allowed(error: ProviderError, policy: RetryPolicy) -> bool:
        if not error.retryable:
            return False
        return {
            RuntimeFailureCategory.PROVIDER_TIMEOUT: policy.retry_timeouts,
            RuntimeFailureCategory.PROVIDER_TRANSIENT: policy.retry_transient_errors,
            RuntimeFailureCategory.PROVIDER_RATE_LIMIT: policy.retry_rate_limits,
        }.get(error.category, False)

    @staticmethod
    def _unavailable_estimate(at: datetime) -> TokenEstimate:
        return TokenEstimate(
            tokens=None,
            method=TokenEstimateMethod.UNAVAILABLE,
            conservative=False,
            estimated_at=at,
        )

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("runtime clock must return a timezone-aware timestamp")
        return value.astimezone(UTC)
