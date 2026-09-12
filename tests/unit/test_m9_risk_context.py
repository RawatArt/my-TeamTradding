"""M9 baseline lifecycle and AccountRiskContext construction tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.fakes.market import FakeMarketDataSource
from tests.fakes.risk import risk_snapshot

from ai_trading_team.observation import ObservationRuntimeError
from ai_trading_team.observation.risk_context import AccountRiskContextProvider
from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.risk import account_fingerprint
from ai_trading_team.schemas.enums import (
    ObservationFailureCategory,
    RiskBaselineProvenance,
    RiskBaselineState,
)
from ai_trading_team.schemas.observation import RiskBaselineRecord
from ai_trading_team.storage.observation import InMemoryObservationRepository


def _baseline(identifier: str = "baseline-m9-active") -> RiskBaselineRecord:
    start = datetime(2026, 9, 10, tzinfo=UTC)
    return RiskBaselineRecord(
        baseline_id=identifier,
        account_ref=account_fingerprint(12345678, "Broker-Demo"),
        utc_trading_day=start.date(),
        trading_day_started_at=start,
        effective_from=start,
        adjusted_day_start_equity=Decimal("50"),
        cash_flow_adjusted_peak_equity=Decimal("51"),
        provenance=RiskBaselineProvenance.OPERATOR_ATTESTED,
        evidence_ref="operator-evidence-m9",
        evidence_digest="sha256:" + "a" * 64,
        state=RiskBaselineState.ACTIVE,
        created_at=start,
    )


def test_context_uses_exact_single_active_baseline_and_account_wide_positions() -> None:
    snapshot = risk_snapshot()
    source = FakeMarketDataSource()
    source.account_result = snapshot.account.model_copy(
        update={"retrieved_at": snapshot.snapshot_completed_at}
    )
    source.positions_result = ()
    repository = InMemoryObservationRepository()
    repository.append_baseline(_baseline())
    provider = AccountRiskContextProvider(
        source,
        repository,
        clock=lambda: snapshot.snapshot_completed_at + timedelta(seconds=1),
    )

    evidence = provider.build(snapshot)

    assert evidence.context.snapshot_id == snapshot.snapshot_id
    assert evidence.context.cash_flow_adjusted_peak_equity == Decimal("51")
    assert evidence.baseline_digest == content_digest(_baseline())


@pytest.mark.parametrize("count", [0, 2])
def test_zero_or_multiple_active_baselines_fail_closed(count: int) -> None:
    snapshot = risk_snapshot()
    source = FakeMarketDataSource()
    source.account_result = snapshot.account.model_copy(
        update={"retrieved_at": snapshot.snapshot_completed_at}
    )
    source.positions_result = ()
    repository = InMemoryObservationRepository()
    for index in range(count):
        repository.append_baseline(_baseline(f"baseline-m9-{index}"))
    provider = AccountRiskContextProvider(
        source,
        repository,
        clock=lambda: snapshot.snapshot_completed_at + timedelta(seconds=1),
    )

    with pytest.raises(ObservationRuntimeError) as caught:
        provider.build(snapshot)

    expected = (
        ObservationFailureCategory.RISK_BASELINE_MISSING
        if count == 0
        else ObservationFailureCategory.RISK_BASELINE_AMBIGUOUS
    )
    assert caught.value.category is expected


def test_baseline_replacement_is_explicit_and_auditable() -> None:
    repository = InMemoryObservationRepository()
    current = _baseline()
    repository.append_baseline(current)
    at = current.effective_from + timedelta(hours=1)
    replacement = _baseline("baseline-m9-replacement").model_copy(
        update={"effective_from": at, "created_at": at}
    )

    repository.supersede_baseline(current.baseline_id, replacement, at=at)

    assert repository.active_baselines(current.account_ref, current.utc_trading_day, at=at) == (
        replacement,
    )
