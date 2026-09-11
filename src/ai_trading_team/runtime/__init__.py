"""Single-agent, provider-neutral model runtime.

Concrete modules are intentionally imported explicitly to keep the prompt registry dependency
acyclic and provider SDKs lazy.
"""

from ai_trading_team.runtime.acceptance import (
    ProviderAcceptanceRegistry,
    profile_digest,
)

__all__ = ["ProviderAcceptanceRegistry", "profile_digest"]
