import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.risk import EVALUATED_AT, account_context, proposal, risk_snapshot

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import RiskEngine, account_fingerprint
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision


def test_account_reference_is_stable_but_changes_with_account_identity() -> None:
    first = account_fingerprint(12345678, "Broker-Demo")

    assert first == account_fingerprint(12345678, "broker-demo")
    assert first != account_fingerprint(12345679, "Broker-Demo")
    assert first.startswith("acct-v1:")
    assert "12345678" not in first
    assert "Broker" not in first


def test_account_context_rejects_invalid_reference_and_naive_timestamp() -> None:
    snapshot = risk_snapshot()
    payload = account_context(snapshot).model_dump(mode="python")
    payload["account_ref"] = "raw-account-123"
    payload["context_as_of"] = datetime(2026, 9, 10)

    with pytest.raises(ValidationError):
        AccountRiskContext.model_validate(payload)


def test_account_context_normalizes_aware_timestamps_to_utc() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot)

    assert context.context_as_of.tzinfo is UTC
    assert context.trading_day_started_at.tzinfo is UTC


def test_risk_decision_decimal_values_round_trip_without_binary_float() -> None:
    snapshot = risk_snapshot()
    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, account_context(snapshot), EVALUATED_AT
    )

    payload = decision.model_dump_json()
    decoded = json.loads(payload)
    restored = RiskDecision.model_validate_json(payload)

    assert decoded["account_metrics"]["current_equity"] == "50.00"
    assert Decimal(decoded["position_sizing"]["allowed_risk_amount"]) == Decimal("0.25")
    assert isinstance(decoded["position_sizing"]["allowed_risk_amount"], str)
    assert isinstance(restored.account_metrics.drawdown_percent, Decimal)
    assert restored.position_sizing is not None
    assert isinstance(restored.position_sizing.selected_volume, Decimal)
    assert isinstance(restored.position_sizing.estimated_risk_amount, Decimal)
