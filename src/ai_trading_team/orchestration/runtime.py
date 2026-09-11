"""Orchestrator-owned bridge from M4 roles to the single-agent M5 runtime."""

from collections.abc import Mapping
from typing import Protocol, Self, cast

from pydantic import model_validator

from ai_trading_team.orchestration.identifiers import (
    logical_invocation_id,
    logical_output_id,
)
from ai_trading_team.runtime.acceptance import ProviderAcceptanceRegistry
from ai_trading_team.runtime.contracts import contract_for_role, schema_reference
from ai_trading_team.runtime.router import RuntimeRouter
from ai_trading_team.schemas.agents import AgentDescriptor
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import AgentRole
from ai_trading_team.schemas.orchestration import SnapshotAgentInput
from ai_trading_team.schemas.runtime import (
    AgentInvocationRequest,
    AgentInvocationResult,
    AIBudgetPolicy,
    ModelCapabilityProfile,
    PricingProfile,
    ProviderAdapterIdentity,
    RetryPolicy,
    RuntimeProfile,
)


class AgentRuntimeAssignment(CoreModel):
    """Complete immutable configuration for one role invocation."""

    descriptor: AgentDescriptor
    runtime: RuntimeProfile
    capability: ModelCapabilityProfile
    retry_policy: RetryPolicy
    budget_policy: AIBudgetPolicy
    pricing: PricingProfile
    adapter_identity: ProviderAdapterIdentity

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.descriptor.runtime_profile_ref != self.runtime.profile_ref:
            raise ValueError("descriptor runtime reference does not match runtime profile")
        if self.descriptor.cost_policy_ref != self.budget_policy.policy_ref:
            raise ValueError("descriptor cost policy does not match budget policy")
        if self.runtime.capability_profile_ref != self.capability.profile_ref:
            raise ValueError("runtime capability reference does not match capability profile")
        if self.runtime.retry_policy_ref != self.retry_policy.policy_ref:
            raise ValueError("runtime retry reference does not match retry policy")
        if self.runtime.cost_policy_ref != self.budget_policy.policy_ref:
            raise ValueError("runtime cost reference does not match budget policy")
        if self.runtime.pricing_profile_ref != self.pricing.profile_ref:
            raise ValueError("runtime pricing reference does not match pricing profile")
        identities = {
            self.runtime.provider,
            self.capability.provider,
            self.pricing.provider,
            self.adapter_identity.provider,
        }
        models = {
            self.runtime.model_identifier,
            self.capability.model_identifier,
            self.pricing.model_identifier,
        }
        if len(identities) != 1 or len(models) != 1:
            raise ValueError("runtime assignment provider/model identities must agree")
        return self


class ShadowAgentInvoker(Protocol):
    """Only invocation capability visible to the M6 orchestrator."""

    async def invoke(
        self,
        role: AgentRole,
        context: CoreModel,
        *,
        stage_number: int,
        debate_round: int | None = None,
    ) -> AgentInvocationResult: ...


class RuntimeAgentInvoker:
    """Validate assignment and eligibility, then invoke exactly one M5 request."""

    def __init__(
        self,
        router: RuntimeRouter,
        assignments: Mapping[AgentRole, AgentRuntimeAssignment],
        acceptance: ProviderAcceptanceRegistry,
    ) -> None:
        self._router = router
        self._assignments = dict(assignments)
        self._acceptance = acceptance

    async def invoke(
        self,
        role: AgentRole,
        context: CoreModel,
        *,
        stage_number: int,
        debate_round: int | None = None,
    ) -> AgentInvocationResult:
        assignment = self._assignments[role]
        if assignment.descriptor.role is not role:
            raise ValueError("runtime assignment role does not match requested role")
        contract = contract_for_role(role)
        if not isinstance(context, contract.input_type):
            raise TypeError("role context does not match its accepted M4 input contract")
        self._acceptance.require_eligible(
            assignment.runtime,
            assignment.capability,
            assignment.adapter_identity,
        )
        traced_context = cast(SnapshotAgentInput, context)
        cycle_id = traced_context.cycle_id
        snapshot_id = traced_context.snapshot_id
        invocation_id = logical_invocation_id(
            cycle_id,
            snapshot_id,
            stage_number,
            role,
            debate_round,
        )
        request = AgentInvocationRequest(
            invocation_id=invocation_id,
            output_id=logical_output_id(invocation_id),
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            descriptor=assignment.descriptor,
            requested_at=traced_context.market.snapshot_completed_at,
            input_schema=schema_reference(contract.input_type),
            output_schema=schema_reference(contract.body_adapter),
            context=context,
        )
        return await self._router.invoke(
            request,
            runtime=assignment.runtime,
            capability=assignment.capability,
            retry_policy=assignment.retry_policy,
            budget_policy=assignment.budget_policy,
            pricing=assignment.pricing,
        )
