"""Provider-free end-to-end M9 continuous SHADOW acceptance."""

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from ai_trading_team.config import MarketDataSettings, RiskConstitutionSettings
from ai_trading_team.features import MarketFeatureEngine
from ai_trading_team.features.serialization import canonical_model_bytes
from ai_trading_team.market import MarketDataService
from ai_trading_team.observation import CompletedCandleDiscovery
from ai_trading_team.observation.eligibility import (
    StaticCycleProviderEligibility,
    SymbolTimestampEligibilityRegistry,
)
from ai_trading_team.observation.errors import ObservationRuntimeError
from ai_trading_team.observation.identifiers import (
    cycle_id_for_decision,
    decision_candle_content_digest,
    decision_key,
)
from ai_trading_team.observation.protocols import RiskContextService, SnapshotService
from ai_trading_team.observation.runtime import ContinuousShadowRuntime
from ai_trading_team.orchestration import ShadowCycleOrchestrator
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk import RiskEngine, account_fingerprint
from ai_trading_team.schemas.enums import (
    DecisionClaimState,
    M9DecisionDisposition,
    ObservationFailureCategory,
    Timeframe,
)
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.observation import (
    CompletedDecisionCandle,
    ContinuousDecisionRecord,
    RiskContextEvidence,
    SymbolTimestampAcceptanceRecord,
)
from ai_trading_team.schemas.risk import AccountRiskContext
from ai_trading_team.storage.observation import InMemoryObservationRepository
from ai_trading_team.storage.shadow_audit import InMemoryShadowAuditRepository
from tests.fakes.features import feature_candles
from tests.fakes.market import SYMBOL, FakeMarketDataSource, SequenceClock
from tests.fakes.shadow import ScriptedShadowInvoker

NOW = datetime(2026, 9, 10, 12, 0, 10, tzinfo=UTC)


class ScriptedDiscovery:
    def __init__(self, polls: Iterable[tuple[CompletedDecisionCandle, ...]]) -> None:
        self._polls = iter(polls)

    def poll(self) -> tuple[CompletedDecisionCandle, ...]:
        return next(self._polls, ())

    def is_timely(self, candle: CompletedDecisionCandle) -> bool:
        return True


class ScriptedSnapshots:
    def __init__(self, snapshots: dict[str, MarketSnapshot]) -> None:
        self._snapshots = snapshots

    def build_snapshot(
        self,
        cycle_id: str,
        snapshot_id: str,
        primary_timeframe: Timeframe,
    ) -> MarketSnapshot:
        source = self._snapshots[cycle_id]
        return MarketSnapshot.model_validate(
            source.model_copy(update={"snapshot_id": f"accepted-{snapshot_id}"}).model_dump()
        )


class ScriptedRiskContexts:
    def build(self, snapshot: MarketSnapshot) -> RiskContextEvidence:
        account_ref = account_fingerprint(snapshot.account.account_id, snapshot.account.server)
        context = AccountRiskContext(
            cycle_id=snapshot.cycle_id,
            snapshot_id=snapshot.snapshot_id,
            account_ref=account_ref,
            context_as_of=NOW,
            trading_day_started_at=datetime(2026, 9, 10, tzinfo=UTC),
            cash_flow_adjusted_peak_equity=Decimal("51"),
            adjusted_day_start_equity=Decimal("50"),
            account_open_position_count=0,
        )
        return RiskContextEvidence(
            baseline_id="baseline-m9-scripted",
            baseline_digest="sha256:" + "a" * 64,
            account_observation_digest=content_digest(snapshot.account),
            positions_observation_digest=content_digest(()),
            context=context,
        )


class InvalidRiskContexts:
    def build(self, snapshot: MarketSnapshot) -> RiskContextEvidence:
        raise ObservationRuntimeError(
            ObservationFailureCategory.RISK_CONTEXT_INVALID,
            "scripted account/snapshot mismatch",
        )


def _snapshot(
    close_at: datetime,
    *,
    stale: bool = False,
) -> tuple[CompletedDecisionCandle, MarketSnapshot]:
    source = FakeMarketDataSource()
    delta = close_at - datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    source.symbol_info_result = source.symbol_info_result.model_copy(
        update={"retrieved_at": close_at + timedelta(seconds=1)}
    )
    source.account_result = source.account_result.model_copy(
        update={"retrieved_at": close_at + timedelta(seconds=1)}
    )
    source.tick_result = source.tick_result.model_copy(
        update={
            "source_time": close_at + timedelta(seconds=3),
            "retrieved_at": close_at + timedelta(seconds=4),
        }
    )
    source.positions_result = ()
    for timeframe in (Timeframe.M15, Timeframe.H1, Timeframe.H4):
        source.candle_results[timeframe] = tuple(
            item.model_copy(
                update={
                    "open_time": item.open_time + delta,
                    "retrieved_at": close_at + timedelta(seconds=2),
                }
            )
            for item in feature_candles(timeframe)
        )
    preliminary = MarketDataService(
        source,
        MarketDataSettings(max_tick_age_seconds=1 if stale else 120),
        SYMBOL,
        clock=SequenceClock(
            close_at,
            close_at + timedelta(seconds=3),
            close_at + timedelta(seconds=5),
        ),
    ).build_snapshot("cycle-m9-preliminary", "snapshot-m9-preliminary", Timeframe.M15)
    decision_bar = preliminary.candles.m15[-1]
    key = decision_key(SYMBOL, Timeframe.M15, decision_bar.open_time, close_at)
    cycle_id = cycle_id_for_decision(key)
    snapshot = MarketSnapshot.model_validate(
        preliminary.model_copy(update={"cycle_id": cycle_id}).model_dump()
    )
    candle = CompletedDecisionCandle(
        decision_key=key,
        cycle_id=cycle_id,
        symbol=SYMBOL,
        candle_open_at=decision_bar.open_time,
        candle_close_at=close_at,
        candle_digest=decision_candle_content_digest(decision_bar),
        observed_at=close_at + timedelta(seconds=6),
    )
    return candle, snapshot


def _runtime(
    candidates: tuple[CompletedDecisionCandle, ...],
    snapshots: dict[str, MarketSnapshot],
    *,
    providers_eligible: bool = True,
    risk_contexts: RiskContextService | None = None,
    polls: Iterable[tuple[CompletedDecisionCandle, ...]] | None = None,
    symbol_registry: SymbolTimestampEligibilityRegistry | None = None,
) -> tuple[ContinuousShadowRuntime, InMemoryObservationRepository, ScriptedShadowInvoker]:
    repository = InMemoryObservationRepository()
    account_ref = account_fingerprint(12345678, "Broker-Demo")
    timestamp_registry = SymbolTimestampEligibilityRegistry(
        (
            SymbolTimestampAcceptanceRecord(
                acceptance_id="symbol-time-m9-accepted",
                symbol=SYMBOL,
                timeframes=(Timeframe.M15, Timeframe.H1, Timeframe.H4),
                account_ref=account_ref,
                adapter_version="1.0.0",
                validation_policy_digest="sha256:" + "b" * 64,
                test_result_id="timestamp-test-m9",
                tested_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=1),
            ),
        )
    )
    invoker = ScriptedShadowInvoker()
    shadow = ShadowCycleOrchestrator(
        invoker=invoker,
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=InMemoryShadowAuditRepository(),
        clock=lambda: NOW,
    )
    runtime = ContinuousShadowRuntime(
        symbol=SYMBOL,
        account_ref=account_ref,
        mt5_adapter_version="1.0.0",
        discovery=cast(
            CompletedCandleDiscovery,
            ScriptedDiscovery(
                polls
                if polls is not None
                else tuple((item,) for item in candidates) + (tuple(candidates),)
            ),
        ),
        snapshots=cast(SnapshotService, ScriptedSnapshots(snapshots)),
        features=MarketFeatureEngine(),
        risk_contexts=risk_contexts or cast(RiskContextService, ScriptedRiskContexts()),
        providers=StaticCycleProviderEligibility(providers_eligible),
        shadow_cycles=shadow,
        repository=repository,
        symbol_eligibility=symbol_registry or timestamp_registry,
        snapshot_id_factory=_snapshot_id_factory(),
        clock=lambda: NOW,
    )
    return runtime, repository, invoker


def _snapshot_id_factory() -> Callable[[], str]:
    values = iter(
        ("actual-m2-snapshot-001", "actual-m2-snapshot-002", "actual-m2-snapshot-003")
    )
    return lambda: next(values)


async def _scripted_run() -> tuple[
    tuple[ContinuousDecisionRecord, ...],
    InMemoryObservationRepository,
    ScriptedShadowInvoker,
]:
    pairs = tuple(
        _snapshot(datetime(2026, 9, 10, 11, 30, tzinfo=UTC) + timedelta(minutes=15 * i))
        for i in range(3)
    )
    runtime, repository, invoker = _runtime(
        tuple(item[0] for item in pairs),
        {item[0].cycle_id: item[1] for item in pairs},
    )
    runtime.start()
    records: list[ContinuousDecisionRecord] = []
    for _ in pairs:
        records.extend(await runtime.poll_once())
    assert await runtime.poll_once() == ()
    runtime.shutdown()
    return tuple(records), repository, invoker


def test_fake_provider_continuous_shadow_is_exactly_once_and_reproducible() -> None:
    first_records, first_repository, first_invoker = asyncio.run(_scripted_run())
    second_records, _, second_invoker = asyncio.run(_scripted_run())

    assert len(first_records) == 3
    assert first_records == second_records
    assert canonical_model_bytes(first_records[0]) == canonical_model_bytes(second_records[0])
    assert all(item.disposition is M9DecisionDisposition.SHADOW_RECORDED for item in first_records)
    assert len(first_invoker.calls) == len(second_invoker.calls) == 18
    assert len({item[3] for item in first_invoker.calls}) == 18
    first_claim = first_repository.get_claim(first_records[0].decision_key)
    assert first_claim is not None
    assert first_claim.actual_snapshot_id == first_records[0].actual_snapshot_id
    assert first_claim.actual_snapshot_id == "accepted-actual-m2-snapshot-001"
    assert first_claim.actual_snapshot_id != "actual-m2-snapshot-001"
    assert first_claim.state is DecisionClaimState.COMPLETED


def test_provider_ineligibility_holds_before_any_agent_call() -> None:
    candle, snapshot = _snapshot(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    runtime, _, invoker = _runtime(
        (candle,),
        {candle.cycle_id: snapshot},
        providers_eligible=False,
    )
    runtime.start()

    records = asyncio.run(runtime.poll_once())

    assert records[0].disposition is M9DecisionDisposition.POLICY_HOLD
    assert (
        records[0].failure_category
        is ObservationFailureCategory.PROVIDER_CONFIGURATION_INELIGIBLE
    )
    assert invoker.calls == []


def test_account_context_preflight_holds_before_any_agent_call() -> None:
    candle, snapshot = _snapshot(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    runtime, _, invoker = _runtime(
        (candle,),
        {candle.cycle_id: snapshot},
        risk_contexts=cast(RiskContextService, InvalidRiskContexts()),
    )
    runtime.start()

    records = asyncio.run(runtime.poll_once())

    assert records[0].disposition is M9DecisionDisposition.POLICY_HOLD
    assert records[0].failure_category is ObservationFailureCategory.RISK_CONTEXT_INVALID
    assert invoker.calls == []


def test_snapshot_must_contain_exact_claimed_decision_candle() -> None:
    candle, snapshot = _snapshot(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    original = snapshot.candles.m15[-1]
    last = original.model_copy(update={"close": original.close + Decimal("0.00001")})
    changed_candles = snapshot.candles.model_copy(
        update={"m15": (*snapshot.candles.m15[:-1], last)}
    )
    changed = MarketSnapshot.model_validate(
        snapshot.model_copy(update={"candles": changed_candles}).model_dump()
    )
    runtime, repository, invoker = _runtime(
        (candle,),
        {candle.cycle_id: changed},
    )
    runtime.start()

    assert asyncio.run(runtime.poll_once()) == ()
    claim = repository.get_claim(candle.decision_key)
    assert claim is not None
    assert claim.state is DecisionClaimState.FAILED
    assert claim.actual_snapshot_id is None
    assert claim.failure_category is ObservationFailureCategory.SNAPSHOT_CANDLE_MISMATCH
    assert invoker.calls == []


def test_backpressure_marks_older_candidate_missed_and_processes_latest_only() -> None:
    older, _ = _snapshot(datetime(2026, 9, 10, 11, 45, tzinfo=UTC))
    latest, snapshot = _snapshot(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    runtime, repository, invoker = _runtime(
        (older, latest),
        {latest.cycle_id: snapshot},
        polls=((older, latest),),
    )
    runtime.start()

    records = asyncio.run(runtime.poll_once())

    assert len(records) == 1
    missed = repository.get_claim(older.decision_key)
    assert missed is not None
    assert missed.state is DecisionClaimState.MISSED
    assert missed.failure_category is ObservationFailureCategory.BACKPRESSURE
    assert len(invoker.calls) == 6


def test_stale_snapshot_is_policy_hold_without_provider_dispatch() -> None:
    candle, snapshot = _snapshot(
        datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        stale=True,
    )
    runtime, _, invoker = _runtime((candle,), {candle.cycle_id: snapshot})
    runtime.start()

    records = asyncio.run(runtime.poll_once())
    runtime.shutdown()

    assert records[0].disposition is M9DecisionDisposition.POLICY_HOLD
    assert records[0].failure_category is ObservationFailureCategory.STALE_SNAPSHOT
    assert invoker.calls == []
    assert runtime.health().state.value == "STOPPED"


def test_unaccepted_symbol_timestamp_semantics_fail_startup_closed() -> None:
    candle, snapshot = _snapshot(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    runtime, _, invoker = _runtime(
        (candle,),
        {candle.cycle_id: snapshot},
        symbol_registry=SymbolTimestampEligibilityRegistry(),
    )

    with pytest.raises(ObservationRuntimeError) as caught:
        runtime.start()

    assert caught.value.category is ObservationFailureCategory.SYMBOL_TIMESTAMP_INELIGIBLE
    assert invoker.calls == []
