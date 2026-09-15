"""Dependency-injection boundaries for the narrow M11 execution layer."""

from datetime import datetime
from typing import Protocol

from ai_trading_team.schemas.common import ContentDigest, Identifier
from ai_trading_team.schemas.enums import ExecutionControlState
from ai_trading_team.schemas.execution import (
    CompositeBrokerEvidence,
    DemoExecutionApproval,
    DemoExecutionApprovalRevocation,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPreflight,
    DemoExecutionRecord,
    DemoOrderCheckResult,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    DemoSymbolExecutionCapabilities,
    ExecutionControlEvent,
    FinalDispatchObservation,
    FreshExecutionObservation,
    FreshRiskRevalidation,
)
from ai_trading_team.schemas.execution_acceptance import VendorBoundaryAudit


class DemoExecutionObservationSource(Protocol):
    """Build one fresh, typed, read-only execution-validation observation."""

    def capture(self, cycle_id: str, execution_snapshot_id: str) -> FreshExecutionObservation: ...


class DemoExecutionAdapter(Protocol):
    """No generic vendor access and one semantically narrow submission method."""

    adapter_version: str

    def get_execution_capabilities(
        self, symbol: str
    ) -> DemoSymbolExecutionCapabilities: ...

    def order_check(self, intent: DemoOrderIntent) -> DemoOrderCheckResult: ...

    def observe_final_dispatch(self, intent: DemoOrderIntent) -> FinalDispatchObservation: ...

    def submit_demo_market_intent(self, intent: DemoOrderIntent) -> DemoSubmissionReceipt: ...

    def get_vendor_boundary_audit(
        self, execution_intent_id: str
    ) -> VendorBoundaryAudit | None: ...

    def find_broker_evidence(
        self,
        intent: DemoOrderIntent,
        receipt: DemoSubmissionReceipt,
    ) -> tuple[CompositeBrokerEvidence, ...]: ...

    def shutdown(self) -> None: ...


class DemoExecutionRepository(Protocol):
    """Append-only persistence and atomic claim ownership."""

    def add_environment_acceptance(
        self, acceptance: DemoExecutionEnvironmentAcceptance
    ) -> None: ...

    def add_approval(self, approval: DemoExecutionApproval) -> None: ...

    def revoke_approval(self, revocation: DemoExecutionApprovalRevocation) -> None: ...

    def effective_approvals(
        self,
        *,
        account_ref: str,
        environment_ref: str,
        symbol: str,
        at: datetime,
    ) -> tuple[DemoExecutionApproval, ...]: ...

    def approval_is_revoked(self, approval_id: str, approval_digest: ContentDigest) -> bool: ...

    def append_control_event(self, event: ExecutionControlEvent) -> None: ...

    def control_state(self) -> ExecutionControlState: ...

    def current_control_event(self) -> ExecutionControlEvent | None: ...

    def claim(
        self,
        intent: DemoOrderIntent,
        preflight: DemoExecutionPreflight,
        risk_revalidation: FreshRiskRevalidation,
        owner: Identifier,
        claimed_at: datetime,
    ) -> DemoExecutionRecord: ...

    def claim_is_owned(self, execution_intent_id: str, owner: Identifier) -> bool: ...

    def save(self, record: DemoExecutionRecord) -> None: ...

    def get(self, execution_intent_id: str) -> DemoExecutionRecord | None: ...

    def get_by_source_digest(self, digest: ContentDigest) -> DemoExecutionRecord | None: ...

    def recover_incomplete(self, recovered_at: datetime) -> tuple[DemoExecutionRecord, ...]: ...
