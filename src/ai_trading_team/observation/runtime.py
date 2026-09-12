"""Bounded, explicitly polled M9 continuous SHADOW coordinator."""

from collections.abc import Callable
from datetime import UTC, datetime

from ai_trading_team.features.errors import FeatureEngineError
from ai_trading_team.market.errors import MarketDataError
from ai_trading_team.observation.candles import CompletedCandleDiscovery
from ai_trading_team.observation.eligibility import (
    ProviderConfigurationIneligible,
    SymbolTimestampEligibilityRegistry,
    SymbolTimestampIneligible,
)
from ai_trading_team.observation.errors import ObservationRuntimeError
from ai_trading_team.observation.identifiers import (
    SnapshotIdFactory,
    decision_candle_content_digest,
    random_snapshot_id,
    record_id_for_decision,
)
from ai_trading_team.observation.protocols import (
    FeatureService,
    ProviderEligibilityService,
    RiskContextService,
    ShadowCycleService,
    SnapshotService,
)
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.agents import AgentMarketView
from ai_trading_team.schemas.common import AccountReference, Symbol
from ai_trading_team.schemas.enums import (
    ContinuousRuntimeState,
    DecisionClaimState,
    FreshnessState,
    M9DecisionDisposition,
    ObservationFailureCategory,
    Timeframe,
)
from ai_trading_team.schemas.features import MarketFeatureSet
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.observation import (
    CompletedDecisionCandle,
    ContinuousDecisionRecord,
    ContinuousRuntimeHealth,
    DecisionCandleClaim,
    RiskContextEvidence,
)
from ai_trading_team.schemas.timeframes import timeframe_duration
from ai_trading_team.storage.observation import ObservationRepository
from ai_trading_team.utils.time import utc_now


class ContinuousShadowRuntime:
    """Discover and process at most one current M15 decision at a time.

    This class has no scheduler and no execution capability. Callers explicitly invoke
    :meth:`poll_once`; a future deployment layer may provide bounded scheduling.
    """

    def __init__(
        self,
        *,
        symbol: Symbol,
        account_ref: AccountReference,
        mt5_adapter_version: str,
        discovery: CompletedCandleDiscovery,
        snapshots: SnapshotService,
        features: FeatureService,
        risk_contexts: RiskContextService,
        providers: ProviderEligibilityService,
        shadow_cycles: ShadowCycleService,
        repository: ObservationRepository,
        symbol_eligibility: SymbolTimestampEligibilityRegistry,
        snapshot_id_factory: SnapshotIdFactory = random_snapshot_id,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._symbol = symbol
        self._account_ref = account_ref
        self._adapter_version = mt5_adapter_version
        self._discovery = discovery
        self._snapshots = snapshots
        self._features = features
        self._risk_contexts = risk_contexts
        self._providers = providers
        self._shadow_cycles = shadow_cycles
        self._repository = repository
        self._symbol_eligibility = symbol_eligibility
        self._snapshot_id_factory = snapshot_id_factory
        self._clock = clock
        self._state = ContinuousRuntimeState.STOPPED
        self._started_at: datetime | None = None
        self._last_poll_at: datetime | None = None
        self._last_candle_close_at: datetime | None = None
        self._last_completed_cycle_id: str | None = None
        self._last_failure: ObservationFailureCategory | None = None
        self._missed_count = 0
        self._processing = False
        self._shutdown_requested = False

    def start(self) -> tuple[DecisionCandleClaim, ...]:
        """Validate timestamp eligibility and abandon uncertain prior claims."""
        if self._state is not ContinuousRuntimeState.STOPPED:
            raise RuntimeError("continuous runtime may only start from STOPPED")
        self._state = ContinuousRuntimeState.STARTING
        now = self._now()
        try:
            self._symbol_eligibility.require_eligible(
                symbol=self._symbol,
                account_ref=self._account_ref,
                adapter_version=self._adapter_version,
                at=now,
            )
            abandoned = self._repository.recover_incomplete(at=now)
        except SymbolTimestampIneligible as exc:
            self._state = ContinuousRuntimeState.FAULTED
            self._last_failure = ObservationFailureCategory.SYMBOL_TIMESTAMP_INELIGIBLE
            raise ObservationRuntimeError(self._last_failure, str(exc)) from exc
        self._started_at = now
        self._shutdown_requested = False
        self._state = ContinuousRuntimeState.READY
        return abandoned

    async def poll_once(self) -> tuple[ContinuousDecisionRecord, ...]:
        """Perform one bounded poll; repeated candles never redispatch."""
        if self._processing:
            self._last_failure = ObservationFailureCategory.BACKPRESSURE
            return ()
        if self._state is not ContinuousRuntimeState.READY:
            raise RuntimeError("continuous runtime must be READY before polling")
        self._processing = True
        self._state = ContinuousRuntimeState.POLLING
        self._last_poll_at = self._now()
        try:
            candles = self._discovery.poll()
            records: list[ContinuousDecisionRecord] = []
            eligible = [
                item
                for item in candles
                if self._repository.get_claim(item.decision_key) is None
            ]
            timely = [item for item in eligible if self._discovery.is_timely(item)]
            for old in (item for item in eligible if item not in timely):
                self._record_missed(old)
            if len(timely) > 1:
                for skipped in timely[:-1]:
                    self._record_missed(skipped, ObservationFailureCategory.BACKPRESSURE)
                timely = timely[-1:]
            for candle in timely:
                record = await self._process(candle)
                if record is not None:
                    records.append(record)
            return tuple(records)
        except ObservationRuntimeError as exc:
            self._last_failure = exc.category
            return ()
        finally:
            self._processing = False
            if self._state is not ContinuousRuntimeState.FAULTED:
                self._state = (
                    ContinuousRuntimeState.STOPPED
                    if self._shutdown_requested
                    else ContinuousRuntimeState.READY
                )

    def shutdown(self) -> None:
        """Stop accepting polls; in-flight work is never silently redispatched."""
        if self._state is ContinuousRuntimeState.STOPPED:
            return
        self._shutdown_requested = True
        self._state = ContinuousRuntimeState.STOPPING
        if not self._processing:
            self._state = ContinuousRuntimeState.STOPPED

    def health(self) -> ContinuousRuntimeHealth:
        return ContinuousRuntimeHealth(
            state=self._state,
            symbol=self._symbol,
            started_at=self._started_at,
            last_poll_at=self._last_poll_at,
            last_observed_candle_close_at=self._last_candle_close_at,
            last_completed_cycle_id=self._last_completed_cycle_id,
            in_flight_count=int(self._processing),
            pending_count=0,
            missed_count=self._missed_count,
            pending_outcome_count=len(self._repository.pending_outcomes()),
            symbol_eligible=self._state not in {
                ContinuousRuntimeState.STOPPED,
                ContinuousRuntimeState.FAULTED,
            },
            providers_eligible=self._last_failure
            is not ObservationFailureCategory.PROVIDER_CONFIGURATION_INELIGIBLE,
            last_failure_category=self._last_failure,
            updated_at=self._now(),
        )

    async def _process(
        self,
        candle: CompletedDecisionCandle,
    ) -> ContinuousDecisionRecord | None:
        self._repository.discover(candle)
        self._repository.claim(candle.decision_key, at=self._now())
        self._state = ContinuousRuntimeState.PROCESSING
        self._last_candle_close_at = candle.candle_close_at
        snapshot: MarketSnapshot | None = None
        feature_set: MarketFeatureSet | None = None
        market_view: AgentMarketView | None = None
        risk_evidence: RiskContextEvidence | None = None
        try:
            requested_snapshot_id = self._snapshot_id_factory()
            snapshot = self._snapshots.build_snapshot(
                candle.cycle_id,
                requested_snapshot_id,
                Timeframe.M15,
            )
            self._validate_snapshot(candle, snapshot)
            self._repository.bind_snapshot(
                candle.decision_key,
                snapshot.snapshot_id,
                at=self._now(),
            )
            if snapshot.consistency.freshness.overall is FreshnessState.STALE:
                return self._hold(
                    candle,
                    snapshot,
                    ObservationFailureCategory.STALE_SNAPSHOT,
                    "valid snapshot is stale under continuous SHADOW policy",
                )

            risk_evidence = self._risk_contexts.build(snapshot)
            feature_set = self._features.calculate(snapshot)
            self._validate_features(snapshot, feature_set)
            market_view = AgentMarketView.from_snapshot(snapshot, feature_set)
            self._providers.require_eligible(market_view, at=self._now())
            self._repository.mark_processing(candle.decision_key, at=self._now())
            shadow = await self._shadow_cycles.run_shadow_cycle(
                snapshot,
                risk_evidence.context,
                market_view=market_view,
            )
            record = ContinuousDecisionRecord(
                record_id=record_id_for_decision(candle.decision_key),
                decision_key=candle.decision_key,
                cycle_id=candle.cycle_id,
                actual_snapshot_id=snapshot.snapshot_id,
                symbol=candle.symbol,
                decision_candle_digest=candle.candle_digest,
                disposition=M9DecisionDisposition.SHADOW_RECORDED,
                recorded_at=self._now(),
                snapshot_digest=content_digest(snapshot),
                feature_set_digest=content_digest(feature_set),
                agent_feature_view_digest=market_view.agent_feature_view_digest,
                agent_market_view=market_view,
                risk_context_evidence=risk_evidence,
                shadow_record=shadow,
            )
            self._repository.append_decision(record)
            self._repository.mark_terminal(
                candle.decision_key,
                DecisionClaimState.COMPLETED,
                at=self._now(),
            )
            self._last_completed_cycle_id = candle.cycle_id
            self._last_failure = None
            return record
        except ProviderConfigurationIneligible as exc:
            return self._hold(
                candle,
                snapshot,
                ObservationFailureCategory.PROVIDER_CONFIGURATION_INELIGIBLE,
                str(exc),
                feature_set,
                market_view,
                risk_evidence,
            )
        except ObservationRuntimeError as exc:
            if exc.category in {
                ObservationFailureCategory.RISK_BASELINE_MISSING,
                ObservationFailureCategory.RISK_BASELINE_AMBIGUOUS,
                ObservationFailureCategory.RISK_CONTEXT_INVALID,
            }:
                return self._hold(candle, snapshot, exc.category, str(exc))
            self._fail_claim(
                candle,
                exc.category,
                str(exc),
                snapshot,
                feature_set,
                market_view,
                risk_evidence,
            )
        except FeatureEngineError as exc:
            self._fail_claim(
                candle,
                ObservationFailureCategory.FEATURE_FAILURE,
                str(exc),
                snapshot,
                feature_set,
                market_view,
                risk_evidence,
            )
        except MarketDataError as exc:
            self._fail_claim(
                candle,
                ObservationFailureCategory.SNAPSHOT_INVALID,
                str(exc),
                snapshot,
                feature_set,
                market_view,
                risk_evidence,
            )
        except Exception:
            # Provider failures after eligibility are distinct from pre-dispatch policy.
            self._fail_claim(
                candle,
                ObservationFailureCategory.PROVIDER_RUNTIME_FAILURE,
                "continuous SHADOW processing failed after preflight",
                snapshot,
                feature_set,
                market_view,
                risk_evidence,
            )
        return None

    def _hold(
        self,
        candle: CompletedDecisionCandle,
        snapshot: MarketSnapshot | None,
        category: ObservationFailureCategory,
        detail: str,
        feature_set: MarketFeatureSet | None = None,
        market_view: AgentMarketView | None = None,
        risk_evidence: RiskContextEvidence | None = None,
    ) -> ContinuousDecisionRecord:
        record = ContinuousDecisionRecord(
            record_id=record_id_for_decision(candle.decision_key),
            decision_key=candle.decision_key,
            cycle_id=candle.cycle_id,
            actual_snapshot_id=None if snapshot is None else snapshot.snapshot_id,
            symbol=candle.symbol,
            decision_candle_digest=candle.candle_digest,
            disposition=M9DecisionDisposition.POLICY_HOLD,
            recorded_at=self._now(),
            snapshot_digest=None if snapshot is None else content_digest(snapshot),
            feature_set_digest=None if feature_set is None else content_digest(feature_set),
            agent_feature_view_digest=None
            if market_view is None
            else market_view.agent_feature_view_digest,
            agent_market_view=market_view,
            risk_context_evidence=risk_evidence,
            failure_category=category,
            sanitized_detail=detail,
        )
        self._repository.append_decision(record)
        self._repository.mark_terminal(
            candle.decision_key,
            DecisionClaimState.COMPLETED,
            at=self._now(),
        )
        self._last_completed_cycle_id = candle.cycle_id
        self._last_failure = category
        return record

    def _record_missed(
        self,
        candle: CompletedDecisionCandle,
        category: ObservationFailureCategory = ObservationFailureCategory.DECISION_TOO_OLD,
    ) -> None:
        self._repository.discover(candle)
        self._repository.mark_terminal(
            candle.decision_key,
            DecisionClaimState.MISSED,
            at=self._now(),
            failure_category=category,
            detail="decision candle was not eligible for timely bounded processing",
        )
        self._missed_count += 1
        self._last_failure = category

    def _fail_claim(
        self,
        candle: CompletedDecisionCandle,
        category: ObservationFailureCategory,
        detail: str,
        snapshot: MarketSnapshot | None = None,
        feature_set: MarketFeatureSet | None = None,
        market_view: AgentMarketView | None = None,
        risk_evidence: RiskContextEvidence | None = None,
    ) -> None:
        claim = self._repository.get_claim(candle.decision_key)
        bound_snapshot_id = None if claim is None else claim.actual_snapshot_id
        accepted_snapshot = (
            snapshot
            if snapshot is not None and snapshot.snapshot_id == bound_snapshot_id
            else None
        )
        record = ContinuousDecisionRecord(
            record_id=record_id_for_decision(candle.decision_key),
            decision_key=candle.decision_key,
            cycle_id=candle.cycle_id,
            actual_snapshot_id=bound_snapshot_id,
            symbol=candle.symbol,
            decision_candle_digest=candle.candle_digest,
            disposition=M9DecisionDisposition.FAILED,
            recorded_at=self._now(),
            snapshot_digest=None
            if accepted_snapshot is None
            else content_digest(accepted_snapshot),
            feature_set_digest=None
            if accepted_snapshot is None or feature_set is None
            else content_digest(feature_set),
            agent_feature_view_digest=None
            if market_view is None
            else market_view.agent_feature_view_digest,
            agent_market_view=None if accepted_snapshot is None else market_view,
            risk_context_evidence=None if accepted_snapshot is None else risk_evidence,
            failure_category=category,
            sanitized_detail=detail,
        )
        self._repository.append_decision(record)
        self._repository.mark_terminal(
            candle.decision_key,
            DecisionClaimState.FAILED,
            at=self._now(),
            failure_category=category,
            detail=detail,
        )
        self._last_failure = category

    @staticmethod
    def _validate_snapshot(
        candle: CompletedDecisionCandle,
        snapshot: MarketSnapshot,
    ) -> None:
        if (
            snapshot.cycle_id != candle.cycle_id
            or snapshot.symbol != candle.symbol
            or snapshot.primary_timeframe is not Timeframe.M15
        ):
            raise ObservationRuntimeError(
                ObservationFailureCategory.SNAPSHOT_INVALID,
                "accepted snapshot does not match the claimed decision trace",
            )
        matches = tuple(
            item
            for item in snapshot.candles.m15
            if item.open_time == candle.candle_open_at
            and item.open_time + timeframe_duration(Timeframe.M15) == candle.candle_close_at
        )
        if (
            len(matches) != 1
            or decision_candle_content_digest(matches[0]) != candle.candle_digest
        ):
            raise ObservationRuntimeError(
                ObservationFailureCategory.SNAPSHOT_CANDLE_MISMATCH,
                "accepted snapshot does not contain the exact claimed decision candle",
            )

    @staticmethod
    def _validate_features(
        snapshot: MarketSnapshot,
        feature_set: MarketFeatureSet,
    ) -> None:
        if (
            feature_set.cycle_id != snapshot.cycle_id
            or feature_set.snapshot_id != snapshot.snapshot_id
            or feature_set.symbol != snapshot.symbol
            or feature_set.primary_timeframe is not snapshot.primary_timeframe
        ):
            raise ObservationRuntimeError(
                ObservationFailureCategory.FEATURE_TRACE_MISMATCH,
                "feature set does not match the accepted snapshot trace",
            )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("continuous runtime clock must be timezone-aware")
        return value.astimezone(UTC)
