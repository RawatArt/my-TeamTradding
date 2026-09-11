"""Narrow provider and budget protocols used by the M5 runtime router."""

from typing import Protocol

from ai_trading_team.schemas.enums import ModelProvider
from ai_trading_team.schemas.runtime import (
    BudgetReservation,
    ProviderRequest,
    ProviderResponse,
    TokenEstimate,
)


class ModelProviderAdapter(Protocol):
    """Credential-owning provider boundary with no trading-system dependency."""

    @property
    def provider(self) -> ModelProvider: ...

    def prepare(self) -> None: ...

    async def estimate_input_tokens(self, request: ProviderRequest) -> TokenEstimate:
        """Estimate without dispatching a billable generation request."""
        ...

    async def invoke(self, request: ProviderRequest) -> ProviderResponse: ...


class BudgetLedger(Protocol):
    """Atomic reservation lifecycle required by the runtime."""

    def reserve(self, reservation: BudgetReservation) -> BudgetReservation: ...

    def mark_dispatched(self, invocation_id: str, *, at: object) -> BudgetReservation: ...

    def settle(self, invocation_id: str, amount: object, *, at: object) -> BudgetReservation: ...

    def release(self, invocation_id: str, *, at: object) -> BudgetReservation: ...

    def mark_uncertain(self, invocation_id: str, *, at: object) -> BudgetReservation: ...
