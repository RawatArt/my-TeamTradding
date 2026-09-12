"""Read-only construction of the existing M3 account risk context."""

from collections.abc import Callable
from datetime import UTC, datetime

from ai_trading_team.observation.errors import ObservationRuntimeError
from ai_trading_team.observation.protocols import AccountContextSource
from ai_trading_team.orchestration.preflight import ShadowPreflightError, validate_shadow_inputs
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk.account import account_fingerprint
from ai_trading_team.schemas.enums import ObservationFailureCategory
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.observation import RiskContextEvidence
from ai_trading_team.schemas.risk import AccountRiskContext
from ai_trading_team.storage.observation import ObservationRepository
from ai_trading_team.utils.time import utc_now


class AccountRiskContextProvider:
    """Join current read-only account facts with one explicit active baseline."""

    def __init__(
        self,
        source: AccountContextSource,
        repository: ObservationRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._source = source
        self._repository = repository
        self._clock = clock

    def build(self, snapshot: MarketSnapshot) -> RiskContextEvidence:
        """Build context without inferring cash flows, broker time, or risk thresholds."""
        account = self._source.get_account_info()
        positions = self._source.get_positions(None)
        context_as_of = self._now()
        account_ref = account_fingerprint(account.account_id, account.server)
        snapshot_ref = account_fingerprint(
            snapshot.account.account_id,
            snapshot.account.server,
        )
        if account_ref != snapshot_ref:
            raise self._error(
                ObservationFailureCategory.RISK_CONTEXT_INVALID,
                "current account observation does not match the accepted snapshot",
            )
        if (
            account.retrieved_at < snapshot.snapshot_completed_at
            or account.retrieved_at > context_as_of
            or any(
                position.retrieved_at < snapshot.snapshot_completed_at
                or position.retrieved_at > context_as_of
                for position in positions
            )
        ):
            raise self._error(
                ObservationFailureCategory.RISK_CONTEXT_INVALID,
                "account context source is outside its explicit temporal window",
            )

        trading_day = context_as_of.date()
        baselines = self._repository.active_baselines(
            account_ref,
            trading_day,
            at=context_as_of,
        )
        if not baselines:
            raise self._error(
                ObservationFailureCategory.RISK_BASELINE_MISSING,
                "no compatible active risk baseline exists",
            )
        if len(baselines) != 1:
            raise self._error(
                ObservationFailureCategory.RISK_BASELINE_AMBIGUOUS,
                "multiple compatible active risk baselines exist",
            )
        baseline = baselines[0]
        context = AccountRiskContext(
            cycle_id=snapshot.cycle_id,
            snapshot_id=snapshot.snapshot_id,
            account_ref=account_ref,
            context_as_of=context_as_of,
            trading_day_started_at=baseline.trading_day_started_at,
            cash_flow_adjusted_peak_equity=baseline.cash_flow_adjusted_peak_equity,
            adjusted_day_start_equity=baseline.adjusted_day_start_equity,
            account_open_position_count=len(positions),
        )
        try:
            validate_shadow_inputs(snapshot, context, context_as_of)
        except ShadowPreflightError as exc:
            raise self._error(
                ObservationFailureCategory.RISK_CONTEXT_INVALID,
                "account risk context is incompatible with the accepted snapshot",
            ) from exc
        return RiskContextEvidence(
            baseline_id=baseline.baseline_id,
            baseline_digest=content_digest(baseline),
            account_observation_digest=content_digest(account),
            positions_observation_digest=content_digest(positions),
            context=context,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise self._error(
                ObservationFailureCategory.RISK_CONTEXT_INVALID,
                "risk context clock must be timezone-aware",
            )
        return value.astimezone(UTC)

    @staticmethod
    def _error(
        category: ObservationFailureCategory,
        detail: str,
    ) -> ObservationRuntimeError:
        return ObservationRuntimeError(category, detail)
