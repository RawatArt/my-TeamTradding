"""Provider-free, broker-free M11 execution fixtures with real-provider-shaped evidence."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.execution.identifiers import (
    capability_definition_digest,
    symbol_definition_digest,
)
from ai_trading_team.execution.service import DemoExecutionService
from ai_trading_team.execution.vendor_boundary import build_vendor_boundary_audit
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk import RiskEngine, account_fingerprint
from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    DemoFillingMode,
    DemoOrderExecutionMode,
    DemoSubmissionDisposition,
    ExecutionControlState,
    ModelProvider,
    MT5ConnectionState,
)
from ai_trading_team.schemas.execution import (
    CompositeBrokerEvidence,
    DemoExecutionApproval,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPolicy,
    DemoOrderCheckResult,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    DemoSymbolExecutionCapabilities,
    ExecutionControlEvent,
    FinalDispatchObservation,
    FreshExecutionObservation,
    QualifiedDemoExecutionCandidate,
)
from ai_trading_team.schemas.execution_acceptance import VendorBoundaryAudit
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5AccountInfo, MT5SymbolInfo, MT5TerminalHealth, MT5Tick
from ai_trading_team.schemas.observation import AcceptanceEvidenceReference, RiskContextEvidence
from ai_trading_team.schemas.qualification import (
    CurrentQualificationStatus,
    QualificationArtifactReference,
    QualificationDependencyManifest,
    QualificationValidityAssessment,
    QualifiedRoleAssignment,
)
from ai_trading_team.storage.execution import InMemoryDemoExecutionRepository
from tests.fakes.qualification import EVALUATED_AT, qualification_bundle
from tests.fakes.risk import account_context, risk_snapshot

EXECUTION_AT = EVALUATED_AT + timedelta(seconds=1)
ENVIRONMENT_REF = "env-v1:" + "e" * 64


class IncrementingClock:
    def __init__(self, start: datetime, step: timedelta = timedelta(milliseconds=100)) -> None:
        self.current = start
        self.step = step

    def __call__(self) -> datetime:
        value = self.current
        self.current += self.step
        return value


class FakeExecutionObservationSource:
    def __init__(self, captured_at: datetime = EXECUTION_AT) -> None:
        self.captured_at = captured_at
        self.calls = 0
        self.positions = ()

    def capture(self, cycle_id: str, execution_snapshot_id: str) -> FreshExecutionObservation:
        self.calls += 1
        base = risk_snapshot()
        delta = self.captured_at - base.snapshot_completed_at
        shifted = _shift_datetimes(base.model_dump(mode="python"), delta)
        shifted["cycle_id"] = cycle_id
        shifted["snapshot_id"] = execution_snapshot_id
        shifted["open_positions"] = ()
        shifted["tick"] = {
            **shifted["tick"],
            "bid": "1.08120",
            "ask": "1.08130",
            "spread": "0.00010",
            "last": "1.08125",
        }
        shifted["spread"] = "0.00010"
        snapshot = MarketSnapshot.model_validate(shifted)
        context = account_context(
            snapshot,
            cycle_id=cycle_id,
            snapshot_id=execution_snapshot_id,
            context_as_of=snapshot.snapshot_completed_at,
            open_position_count=len(self.positions),
        )
        evidence = RiskContextEvidence(
            baseline_id="baseline-m11-active",
            baseline_digest="sha256:" + "1" * 64,
            account_observation_digest=content_digest(snapshot.account),
            positions_observation_digest=content_digest(self.positions),
            context=context,
        )
        capabilities = execution_capabilities(
            snapshot.symbol_info,
            snapshot.snapshot_completed_at,
        )
        return FreshExecutionObservation(
            captured_at=snapshot.snapshot_completed_at,
            environment_ref=ENVIRONMENT_REF,
            snapshot=snapshot,
            risk_context_evidence=evidence,
            account_positions=self.positions,
            capabilities=capabilities,
        )


class FakeDemoExecutionAdapter:
    adapter_version = "1.0.0"

    def __init__(self, final_observation: FinalDispatchObservation) -> None:
        self.final_observation = final_observation
        self.after_check: Callable[[], None] | None = None
        self.check_accepted = True
        self.submission_disposition = DemoSubmissionDisposition.ACCEPTED
        self.raise_on_submit = False
        self.crash_on_submit = False
        self.evidence_override: tuple[CompositeBrokerEvidence, ...] | None = None
        self.check_calls = 0
        self.submit_calls = 0
        self.reconcile_calls = 0
        self.vendor_audits: dict[str, VendorBoundaryAudit] = {}

    def get_execution_capabilities(self, symbol: str) -> DemoSymbolExecutionCapabilities:
        assert self.final_observation.capabilities.symbol == symbol
        return self.final_observation.capabilities

    def order_check(self, intent: DemoOrderIntent) -> DemoOrderCheckResult:
        self.check_calls += 1
        result = DemoOrderCheckResult(
            execution_intent_id=intent.execution_intent_id,
            intent_digest=intent.intent_digest,
            checked_at=intent.created_at + timedelta(milliseconds=10),
            accepted=self.check_accepted,
            broker_code=0 if self.check_accepted else 10013,
            sanitized_detail="fake check result",
        )
        if self.after_check is not None:
            self.after_check()
        return result

    def observe_final_dispatch(self, intent: DemoOrderIntent) -> FinalDispatchObservation:
        assert intent.symbol == self.final_observation.tick.symbol
        return self.final_observation

    def submit_demo_market_intent(self, intent: DemoOrderIntent) -> DemoSubmissionReceipt:
        self.submit_calls += 1
        self.vendor_audits[intent.execution_intent_id] = build_vendor_boundary_audit(
            intent,
            self.final_observation.symbol_info,
            audited_at=intent.created_at + timedelta(milliseconds=240),
        )
        if self.crash_on_submit:
            raise KeyboardInterrupt("simulated process crash after durable DISPATCHING")
        if self.raise_on_submit:
            raise TimeoutError("sanitized fake dispatch timeout")
        started = intent.created_at + timedelta(milliseconds=250)
        completed = started + timedelta(milliseconds=10)
        evidence = None
        if self.submission_disposition is DemoSubmissionDisposition.ACCEPTED:
            evidence = _evidence(intent, started, completed)
        return DemoSubmissionReceipt(
            execution_intent_id=intent.execution_intent_id,
            intent_digest=intent.intent_digest,
            disposition=self.submission_disposition,
            dispatch_started_at=started,
            dispatch_completed_at=completed,
            broker_code=10009,
            evidence=evidence,
            sanitized_detail="fake normalized submission",
        )

    def get_vendor_boundary_audit(
        self, execution_intent_id: str
    ) -> VendorBoundaryAudit | None:
        return self.vendor_audits.get(execution_intent_id)

    def find_broker_evidence(
        self,
        intent: DemoOrderIntent,
        receipt: DemoSubmissionReceipt,
    ) -> tuple[CompositeBrokerEvidence, ...]:
        self.reconcile_calls += 1
        if self.evidence_override is not None:
            return self.evidence_override
        return (_evidence(intent, receipt.dispatch_started_at, receipt.dispatch_completed_at),)

    def shutdown(self) -> None:
        return None


def execution_capabilities(
    symbol_info: MT5SymbolInfo,
    observed_at: datetime,
) -> DemoSymbolExecutionCapabilities:
    return DemoSymbolExecutionCapabilities(
        symbol=symbol_info.symbol,
        observed_at=observed_at,
        symbol_info_digest=symbol_definition_digest(symbol_info),
        execution_mode=DemoOrderExecutionMode.INSTANT,
        filling_modes=frozenset({DemoFillingMode.FOK}),
        market_order_allowed=True,
        stop_loss_allowed=True,
        take_profit_allowed=True,
    )


def execution_policy() -> DemoExecutionPolicy:
    from decimal import Decimal

    return DemoExecutionPolicy(
        policy_ref="demo-execution-policy-m11",
        policy_version="1.0.0",
        maximum_tick_age_seconds=5,
        maximum_decision_age_seconds=1_800,
        maximum_preflight_seconds=15,
        intent_ttl_seconds=10,
        maximum_spread_ticks=Decimal("20"),
        maximum_price_drift_ticks=Decimal("10"),
        maximum_adverse_slippage_ticks=Decimal("0"),
        supported_execution_modes=frozenset({DemoOrderExecutionMode.INSTANT}),
        filling_mode=DemoFillingMode.FOK,
        magic=110011,
        comment_prefix="ait-m11",
    )


def execution_candidate() -> QualifiedDemoExecutionCandidate:
    _, service, sealed, manifest, graduation, run = qualification_bundle()
    _, _, fake_status = service.evaluate(
        run,
        sealed,
        manifest,
        graduation,
        evaluated_at=EVALUATED_AT,
    )
    real_manifest = _real_provider_manifest(manifest)
    manifest_digest = content_digest(real_manifest)
    validity_payload = fake_status.validity_assessment.model_dump(mode="python")
    validity_payload["dependency_manifest_digest"] = manifest_digest
    validity = QualificationValidityAssessment.model_validate(validity_payload)
    status_payload = fake_status.model_dump(mode="python")
    status_payload["validity_assessment"] = validity
    status = CurrentQualificationStatus.model_validate(status_payload)
    decision = sealed.decisions[0]
    return QualifiedDemoExecutionCandidate(
        candidate_id="demo-execution-candidate-m11",
        decision=decision,
        qualification_status=status,
        dependency_manifest=real_manifest,
        dependency_manifest_digest=manifest_digest,
        qualification_status_digest=content_digest(status),
    )


def execution_environment(
    candidate: QualifiedDemoExecutionCandidate,
    policy: DemoExecutionPolicy,
    capabilities: DemoSymbolExecutionCapabilities,
) -> DemoExecutionEnvironmentAcceptance:
    context = candidate.decision.risk_context_evidence
    assert context is not None
    return DemoExecutionEnvironmentAcceptance(
        acceptance_id="demo-environment-acceptance-m11",
        account_ref=context.context.account_ref,
        environment_ref=ENVIRONMENT_REF,
        account_mode=BrokerAccountMode.DEMO,
        symbol=candidate.decision.symbol,
        package_version="5.0.6180",
        terminal_version="5.0.1",
        terminal_build=5000,
        adapter_version="1.0.0",
        symbol_capability_digest=capability_definition_digest(capabilities),
        execution_policy_digest=content_digest(policy),
        evidence_ref="demo-environment-test-m11",
        evidence_digest="sha256:" + "7" * 64,
        accepted_at=EVALUATED_AT - timedelta(days=1),
        expires_at=EVALUATED_AT + timedelta(days=1),
    )


def execution_approval(
    candidate: QualifiedDemoExecutionCandidate,
    acceptance: DemoExecutionEnvironmentAcceptance,
    policy: DemoExecutionPolicy,
) -> DemoExecutionApproval:
    shadow = candidate.decision.shadow_record
    assert shadow is not None and shadow.shadow_trade_intent is not None
    shadow_intent = shadow.shadow_trade_intent
    return DemoExecutionApproval(
        approval_id="human-demo-approval-m11",
        reviewer_ref="operator-reviewer-m11",
        candidate_id=candidate.candidate_id,
        source_decision_record_digest=content_digest(candidate.decision),
        source_shadow_intent_digest=content_digest(shadow_intent),
        analysis_proposal_digest=content_digest(shadow_intent.proposal),
        analysis_risk_decision_digest=content_digest(shadow_intent.risk_decision),
        qualification_run_id=candidate.qualification_status.qualification_run_id,
        qualification_status_digest=content_digest(candidate.qualification_status),
        generation_id=candidate.dependency_manifest.generation_id,
        generation_digest=content_digest(candidate.dependency_manifest),
        environment_acceptance_id=acceptance.acceptance_id,
        environment_acceptance_digest=content_digest(acceptance),
        account_ref=acceptance.account_ref,
        environment_ref=acceptance.environment_ref,
        symbol=acceptance.symbol,
        execution_policy_digest=content_digest(policy),
        approved_at=EVALUATED_AT - timedelta(minutes=1),
        effective_from=EVALUATED_AT,
        expires_at=EVALUATED_AT + timedelta(hours=1),
    )


def final_dispatch_observation(
    source: FakeExecutionObservationSource,
    candidate: QualifiedDemoExecutionCandidate,
) -> FinalDispatchObservation:
    fresh = source.capture(candidate.decision.cycle_id, "snapshot-final-observation-m11")
    snapshot = fresh.snapshot
    at = snapshot.snapshot_completed_at + timedelta(milliseconds=300)
    account = MT5AccountInfo.model_validate(
        {**snapshot.account.model_dump(mode="python"), "retrieved_at": at}
    )
    symbol_info = MT5SymbolInfo.model_validate(
        {**snapshot.symbol_info.model_dump(mode="python"), "retrieved_at": at}
    )
    tick = MT5Tick.model_validate(
        {
            **snapshot.tick.model_dump(mode="python"),
            "retrieved_at": at,
            "source_time": at - timedelta(milliseconds=10),
        }
    )
    capabilities = execution_capabilities(symbol_info, at)
    health = MT5TerminalHealth(
        retrieved_at=at,
        connection_state=MT5ConnectionState.CONNECTED,
        authenticated=True,
        package_version="5.0.6180",
        terminal_version="5.0.1",
        terminal_build=5000,
        terminal_name="Accepted DEMO Terminal",
        terminal_company="Test Broker",
        trade_api_disabled=False,
    )
    context = candidate.decision.risk_context_evidence
    assert context is not None
    return FinalDispatchObservation(
        observed_at=at,
        account_ref=account_fingerprint(account.account_id, account.server),
        environment_ref=ENVIRONMENT_REF,
        health=health,
        account=account,
        symbol_info=symbol_info,
        capabilities=capabilities,
        tick=tick,
        positions=(),
    )


def execution_bundle() -> tuple[
    DemoExecutionService,
    QualifiedDemoExecutionCandidate,
    DemoExecutionEnvironmentAcceptance,
    DemoExecutionPolicy,
    InMemoryDemoExecutionRepository,
    FakeDemoExecutionAdapter,
]:
    candidate = execution_candidate()
    policy = execution_policy()
    source = FakeExecutionObservationSource()
    final = final_dispatch_observation(source, candidate)
    adapter = FakeDemoExecutionAdapter(final)
    acceptance = execution_environment(candidate, policy, final.capabilities)
    approval = execution_approval(candidate, acceptance, policy)
    repository = InMemoryDemoExecutionRepository()
    repository.add_environment_acceptance(acceptance)
    repository.add_approval(approval)
    repository.append_control_event(
        ExecutionControlEvent(
            event_id="execution-control-disabled-m11",
            previous_state=None,
            state=ExecutionControlState.DISABLED,
            operator_ref="operator-reviewer-m11",
            occurred_at=EVALUATED_AT - timedelta(minutes=2),
            reason="safe default",
        )
    )
    repository.append_control_event(
        ExecutionControlEvent(
            event_id="execution-control-enabled-m11",
            previous_state=ExecutionControlState.DISABLED,
            state=ExecutionControlState.ENABLED,
            operator_ref="operator-reviewer-m11",
            occurred_at=EVALUATED_AT,
            reason="explicit bounded DEMO acceptance",
        )
    )
    service = DemoExecutionService(
        source=source,
        adapter=adapter,
        repository=repository,
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        risk_engine_version=candidate.dependency_manifest.risk_engine_version,
        risk_policy_digest=candidate.dependency_manifest.risk_policy_digest,
        clock=IncrementingClock(EXECUTION_AT),
    )
    return service, candidate, acceptance, policy, repository, adapter


def _real_provider_manifest(
    manifest: QualificationDependencyManifest,
) -> QualificationDependencyManifest:
    accepted_at = EVALUATED_AT - timedelta(days=1)
    expires_at = EVALUATED_AT + timedelta(days=1)

    def evidence(name: str) -> AcceptanceEvidenceReference:
        return AcceptanceEvidenceReference(
            acceptance_id=f"{name}-m11",
            evidence_digest=content_digest({"acceptance_layer": name}),
            accepted_at=accepted_at,
        )

    assignments: list[QualifiedRoleAssignment] = []
    for item in manifest.assignments:
        payload = item.model_dump(mode="python")
        payload.update(
            provider=ModelProvider.OPENAI,
            model_identifier="accepted-provider-model-m11",
            m5_live_smoke=evidence("m5"),
            m6_full_shadow=evidence("m6"),
            m9_feature_input=evidence("m9"),
            m9_continuous_acceptance=QualificationArtifactReference(
                artifact_type="m9_continuous_acceptance",
                artifact_id=f"m9-continuous-{item.role}",
                schema_version="1.0.0",
                content_digest="sha256:" + "9" * 64,
            ),
            acceptance_valid_until=expires_at,
        )
        assignments.append(QualifiedRoleAssignment.model_validate(payload))
    return QualificationDependencyManifest.model_validate(
        {**manifest.model_dump(mode="python"), "assignments": tuple(assignments)}
    )


def _evidence(
    intent: DemoOrderIntent,
    dispatch_started_at: datetime,
    dispatch_completed_at: datetime,
) -> CompositeBrokerEvidence:
    return CompositeBrokerEvidence(
        account_ref=intent.account_ref,
        environment_ref=intent.environment_ref,
        symbol=intent.symbol,
        side=intent.side,
        volume=intent.volume,
        dispatch_started_at=dispatch_started_at,
        dispatch_completed_at=dispatch_completed_at,
        observed_at=dispatch_completed_at + timedelta(milliseconds=10),
        client_trade_reference=None,
        broker_order_id=70001,
        broker_deal_id=80001,
        resulting_position_id=90001,
        fill_price=intent.reference_price,
        stop_loss=intent.stop_loss,
        take_profit=intent.take_profit,
        magic=999,
        comment="broker-truncated",
    )


def _shift_datetimes(value: Any, delta: timedelta) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC) + delta
    if isinstance(value, dict):
        return {key: _shift_datetimes(item, delta) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_shift_datetimes(item, delta) for item in value)
    if isinstance(value, list):
        return [_shift_datetimes(item, delta) for item in value]
    return value
