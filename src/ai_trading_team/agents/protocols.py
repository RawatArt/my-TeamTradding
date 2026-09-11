"""Vendor-neutral agent-to-runtime interface with no provider dependency."""

from typing import Protocol, TypeVar

from ai_trading_team.schemas.agents import AgentDescriptor
from ai_trading_team.schemas.common import CoreModel

InputT = TypeVar("InputT", bound=CoreModel, contravariant=True)
OutputT = TypeVar("OutputT", bound=CoreModel, covariant=True)


class AgentRuntimeAdapter(Protocol[InputT, OutputT]):
    """Injected boundary that an implementation may delegate to the M5 runtime router."""

    async def invoke(self, descriptor: AgentDescriptor, context: InputT) -> OutputT:
        """Return a typed result without prescribing any model vendor."""
        ...
