"""Deterministic AI cost preflight and conservative reservation lifecycle."""

from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from typing import Protocol

from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.enums import BudgetReservationState, RuntimeFailureCategory
from ai_trading_team.schemas.runtime import (
    AIBudgetPolicy,
    BudgetReservation,
    PricingProfile,
    RuntimeProfile,
    TokenEstimate,
)

_MILLION = Decimal("1000000")


class AtomicBudgetLedger(Protocol):
    """Storage operation that checks limits and reserves atomically."""

    def reserve_if_within(
        self,
        reservation: BudgetReservation,
        policy: AIBudgetPolicy,
    ) -> BudgetReservation: ...

    def mark_dispatched(self, invocation_id: str, *, at: datetime) -> BudgetReservation: ...

    def settle(
        self, invocation_id: str, amount: Decimal, *, at: datetime
    ) -> BudgetReservation: ...

    def release(self, invocation_id: str, *, at: datetime) -> BudgetReservation: ...

    def mark_uncertain(self, invocation_id: str, *, at: datetime) -> BudgetReservation: ...


class InMemoryBudgetLedger:
    """Thread-safe ledger used by unit tests and non-persistent local experiments."""

    def __init__(self) -> None:
        self._records: dict[str, BudgetReservation] = {}
        self._lock = RLock()

    def get(self, invocation_id: str) -> BudgetReservation | None:
        with self._lock:
            return self._records.get(invocation_id)

    def reserve_if_within(
        self,
        reservation: BudgetReservation,
        policy: AIBudgetPolicy,
    ) -> BudgetReservation:
        with self._lock:
            if reservation.invocation_id in self._records:
                raise RuntimeInvocationError(
                    RuntimeFailureCategory.DUPLICATE_INVOCATION,
                    "invocation identity has already been reserved",
                )
            active = tuple(
                item
                for item in self._records.values()
                if item.state is not BudgetReservationState.RELEASED
                and item.policy_ref == policy.policy_ref
            )
            same_cycle = sum(item.cycle_id == reservation.cycle_id for item in active)
            same_day = tuple(
                item for item in active if item.created_at.date() == reservation.created_at.date()
            )
            same_month = tuple(
                item
                for item in active
                if (item.created_at.year, item.created_at.month)
                == (reservation.created_at.year, reservation.created_at.month)
            )
            if same_cycle >= policy.maximum_calls_per_cycle:
                raise self._budget_error("maximum calls per cycle exceeded")
            if len(same_day) >= policy.maximum_calls_per_day:
                raise self._budget_error("maximum calls per day exceeded")
            if self._total(same_day) + reservation.reserved_amount > policy.daily_budget:
                raise self._budget_error("daily AI budget exceeded")
            if self._total(same_month) + reservation.reserved_amount > policy.monthly_budget:
                raise self._budget_error("monthly AI budget exceeded")
            self._records[reservation.invocation_id] = reservation
            return reservation

    def mark_dispatched(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            expected=BudgetReservationState.RESERVED,
            state=BudgetReservationState.DISPATCHED,
            at=at,
        )

    def settle(
        self, invocation_id: str, amount: Decimal, *, at: datetime
    ) -> BudgetReservation:
        with self._lock:
            current = self._require(invocation_id)
            if current.state is not BudgetReservationState.DISPATCHED:
                raise ValueError("only dispatched reservations may be settled")
            if amount < 0 or amount > current.reserved_amount:
                raise ValueError("settled amount must be within the reserved amount")
            updated = current.model_copy(
                update={
                    "state": BudgetReservationState.SETTLED,
                    "settled_amount": amount,
                    "updated_at": at.astimezone(UTC),
                }
            )
            self._records[invocation_id] = updated
            return updated

    def release(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            expected=BudgetReservationState.RESERVED,
            state=BudgetReservationState.RELEASED,
            at=at,
        )

    def mark_uncertain(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            expected=BudgetReservationState.DISPATCHED,
            state=BudgetReservationState.UNCERTAIN,
            at=at,
        )

    def _transition(
        self,
        invocation_id: str,
        *,
        expected: BudgetReservationState,
        state: BudgetReservationState,
        at: datetime,
    ) -> BudgetReservation:
        with self._lock:
            current = self._require(invocation_id)
            if current.state is not expected:
                raise ValueError(f"reservation must be {expected.value} before {state.value}")
            updated = current.model_copy(update={"state": state, "updated_at": at.astimezone(UTC)})
            self._records[invocation_id] = updated
            return updated

    def _require(self, invocation_id: str) -> BudgetReservation:
        try:
            return self._records[invocation_id]
        except KeyError as exc:
            raise KeyError("budget reservation does not exist") from exc

    @staticmethod
    def _total(items: tuple[BudgetReservation, ...]) -> Decimal:
        return sum(
            ((
                item.settled_amount
                if item.state is BudgetReservationState.SETTLED
                and item.settled_amount is not None
                else item.reserved_amount
            )
            for item in items),
            start=Decimal("0"),
        )

    @staticmethod
    def _budget_error(detail: str) -> RuntimeInvocationError:
        return RuntimeInvocationError(RuntimeFailureCategory.BUDGET_EXCEEDED, detail)


class BudgetGuard:
    """Validate token/cost bounds and reserve the conservative maximum before dispatch."""

    def __init__(self, ledger: AtomicBudgetLedger) -> None:
        self._ledger = ledger

    def reserve(
        self,
        *,
        invocation_id: str,
        cycle_id: str,
        runtime: RuntimeProfile,
        capability_input_estimate: TokenEstimate,
        policy: AIBudgetPolicy,
        pricing: PricingProfile,
        at: datetime,
    ) -> BudgetReservation:
        if runtime.cost_policy_ref != policy.policy_ref:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.INVALID_REQUEST,
                "runtime cost policy reference does not match supplied policy",
            )
        if runtime.pricing_profile_ref != pricing.profile_ref or (
            runtime.provider is not pricing.provider
            or runtime.model_identifier != pricing.model_identifier
        ):
            raise RuntimeInvocationError(
                RuntimeFailureCategory.INVALID_REQUEST,
                "runtime provider/model does not match supplied pricing profile",
            )
        if capability_input_estimate.tokens is None:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.BUDGET_EXCEEDED,
                "input token estimate unavailable for conservative preflight",
            )
        if capability_input_estimate.tokens > policy.maximum_input_tokens:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.BUDGET_EXCEEDED,
                "maximum input tokens exceeded",
            )
        if runtime.max_output_tokens > policy.maximum_output_tokens:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.BUDGET_EXCEEDED,
                "maximum output tokens exceeded",
            )
        if pricing.currency != policy.currency:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.INVALID_REQUEST,
                "pricing and budget currencies differ",
            )
        moment = at.astimezone(UTC)
        if moment < pricing.valid_from or (
            pricing.valid_until is not None and moment >= pricing.valid_until
        ):
            raise RuntimeInvocationError(
                RuntimeFailureCategory.INVALID_REQUEST,
                "pricing profile is not valid at invocation time",
            )
        estimated = estimate_maximum_cost(
            capability_input_estimate.tokens,
            runtime.max_output_tokens,
            pricing,
        )
        if estimated > policy.maximum_estimated_cost_per_call:
            raise RuntimeInvocationError(
                RuntimeFailureCategory.BUDGET_EXCEEDED,
                "maximum estimated cost per call exceeded",
            )
        reservation = BudgetReservation(
            invocation_id=invocation_id,
            cycle_id=cycle_id,
            policy_ref=policy.policy_ref,
            state=BudgetReservationState.RESERVED,
            reserved_amount=estimated,
            currency=policy.currency,
            created_at=moment,
            updated_at=moment,
        )
        return self._ledger.reserve_if_within(reservation, policy)

    def mark_dispatched(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._ledger.mark_dispatched(invocation_id, at=at)

    def settle(
        self, invocation_id: str, amount: Decimal, *, at: datetime
    ) -> BudgetReservation:
        return self._ledger.settle(invocation_id, amount, at=at)

    def release(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._ledger.release(invocation_id, at=at)

    def mark_uncertain(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._ledger.mark_uncertain(invocation_id, at=at)


def estimate_maximum_cost(
    input_tokens: int,
    maximum_output_tokens: int,
    pricing: PricingProfile,
) -> Decimal:
    """Reserve full uncached input plus the configured maximum output."""
    input_cost = Decimal(input_tokens) * pricing.input_cost_per_million_tokens / _MILLION
    output_cost = (
        Decimal(maximum_output_tokens) * pricing.output_cost_per_million_tokens / _MILLION
    )
    return input_cost + output_cost


def estimate_reported_cost(usage_input: int, usage_output: int, pricing: PricingProfile) -> Decimal:
    """Normalize known reported usage without assuming cache discounts."""
    return estimate_maximum_cost(usage_input, usage_output, pricing)
