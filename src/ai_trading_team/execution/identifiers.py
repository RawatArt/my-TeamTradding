"""Canonical identities and digests for M11 execution artifacts."""

from typing import Any

from ai_trading_team.replay.identifiers import deterministic_id
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk.account import account_fingerprint
from ai_trading_team.schemas.common import EnvironmentReference
from ai_trading_team.schemas.execution import (
    DemoOrderIntent,
    DemoSymbolExecutionCapabilities,
)
from ai_trading_team.schemas.mt5 import MT5AccountInfo, MT5SymbolInfo, MT5TerminalHealth


def environment_fingerprint(
    account: MT5AccountInfo,
    health: MT5TerminalHealth,
) -> EnvironmentReference:
    """Hash sensitive terminal/account metadata into a stable non-secret reference."""
    payload = {
        "domain": "ai-trading-team-demo-environment-v1",
        "account_ref": account_fingerprint(account.account_id, account.server),
        "account_mode": int(account.trade_mode),
        "company": account.company,
        "package_version": health.package_version,
        "terminal_version": health.terminal_version,
        "terminal_build": health.terminal_build,
        "terminal_name": health.terminal_name,
        "terminal_company": health.terminal_company,
    }
    return f"env-v1:{content_digest(payload).removeprefix('sha256:')}"


def capability_definition_digest(capabilities: DemoSymbolExecutionCapabilities) -> str:
    """Digest stable capability facts while excluding retrieval time."""
    return content_digest(capabilities.model_dump(exclude={"observed_at"}, mode="python"))


def symbol_definition_digest(symbol_info: MT5SymbolInfo) -> str:
    """Digest broker symbol facts without retrieval-time noise."""
    return content_digest(symbol_info.model_dump(exclude={"retrieved_at"}, mode="python"))


def seal_demo_order_intent(payload: dict[str, Any]) -> DemoOrderIntent:
    """Add a digest of every intent field except the digest itself."""
    if "intent_digest" in payload:
        raise ValueError("unsealed intent payload must not supply intent_digest")
    normalized = DemoOrderIntent.model_validate(
        {**payload, "intent_digest": "sha256:" + "0" * 64}
    )
    canonical_payload = normalized.model_dump(mode="python", exclude={"intent_digest"})
    return normalized.model_copy(update={"intent_digest": content_digest(canonical_payload)})


def verify_demo_order_intent(intent: DemoOrderIntent) -> bool:
    payload = intent.model_dump(mode="python", exclude={"intent_digest"})
    return content_digest(payload) == intent.intent_digest


def execution_snapshot_id(cycle_id: str, captured_at: object) -> str:
    return deterministic_id(
        "execution-snapshot",
        {"cycle_id": cycle_id, "purpose": "PRE_SEND_REVALIDATION", "captured_at": captured_at},
    )


def revalidation_proposal_id(source_proposal_id: str, execution_snapshot: str) -> str:
    return deterministic_id(
        "execution-revalidation-proposal",
        {"source_proposal_id": source_proposal_id, "snapshot_id": execution_snapshot},
    )


def execution_intent_id(source_intent_digest: str, environment_ref: str, policy_digest: str) -> str:
    return deterministic_id(
        "demo-execution-intent",
        {
            "source_intent_digest": source_intent_digest,
            "environment_ref": environment_ref,
            "policy_digest": policy_digest,
        },
    )


def client_trade_id(intent_id: str) -> str:
    return deterministic_id("demo-client-trade", {"execution_intent_id": intent_id})
