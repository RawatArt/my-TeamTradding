"""Vendor-neutral future runtime interface with no implementation or network access."""

from typing import Protocol, TypeVar

from ai_trading_team.schemas.agents import AgentDescriptor
from ai_trading_team.schemas.common import CoreModel

InputT = TypeVar("InputT", bound=CoreModel, contravariant=True)
OutputT = TypeVar("OutputT", bound=CoreModel, covariant=True)


class AgentRuntimeAdapter(Protocol[InputT, OutputT]):
    """Future injected runtime boundary; M4 provides no implementing class."""

    async def invoke(self, descriptor: AgentDescriptor, context: InputT) -> OutputT:
        """Return a typed result without prescribing any model vendor."""
        ...
