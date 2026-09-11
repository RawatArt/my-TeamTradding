"""Shared abstract base for every M4 AI role contract."""

from abc import ABC, abstractmethod
from typing import ClassVar

from ai_trading_team.agents.access import execution_profile_allowed
from ai_trading_team.schemas.agents import AgentDescriptor
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import AgentRole


class BaseAgent[InputT: CoreModel, OutputT: CoreModel](ABC):
    """Data-only agent boundary; only an orchestrator may own and invoke instances."""

    role: ClassVar[AgentRole]

    def __init__(self, descriptor: AgentDescriptor) -> None:
        if descriptor.role is not self.role:
            raise ValueError("agent descriptor role does not match role contract")
        if not execution_profile_allowed(descriptor.role, descriptor.execution_profile):
            raise ValueError("execution profile is not allowed for this role")
        self._descriptor = descriptor

    @property
    def descriptor(self) -> AgentDescriptor:
        return self._descriptor

    @abstractmethod
    async def analyze(self, context: InputT) -> OutputT:
        """Analyze immutable context; model-backed behavior belongs to a later milestone."""
        raise NotImplementedError
