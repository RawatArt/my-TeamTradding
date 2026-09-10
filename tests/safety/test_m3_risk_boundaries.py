import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.fakes.risk import EVALUATED_AT, account_context, proposal, risk_snapshot

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.risk import AccountRiskContext, RiskDecision

FORBIDDEN_IDENTIFIERS = {
    "MetaTrader5",
    "order_send",
    "order_check",
    "symbol_select",
    "position_close",
    "position_modify",
    "openai",
}


def test_risk_engine_public_input_has_no_ai_confidence() -> None:
    parameters = inspect.signature(RiskEngine.evaluate).parameters

    assert "confidence" not in parameters
    assert "confidence" not in TradeProposal.model_fields
    assert "confidence" not in AccountRiskContext.model_fields
    assert "confidence" not in RiskDecision.model_fields


def test_ai_confidence_cannot_be_smuggled_into_strict_proposal() -> None:
    payload = proposal().model_dump(mode="python")
    payload["confidence"] = "1.0"

    with pytest.raises(ValidationError):
        TradeProposal.model_validate(payload)


def test_risk_package_contains_no_broker_execution_or_ai_api() -> None:
    source_root = Path(__file__).parents[2] / "src" / "ai_trading_team" / "risk"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))

    for identifier in FORBIDDEN_IDENTIFIERS:
        assert identifier not in source


def test_risk_decision_is_not_an_executable_request() -> None:
    assert "order" not in RiskDecision.model_fields
    assert "client_order_id" not in RiskDecision.model_fields
    assert "broker_order_id" not in RiskDecision.model_fields


def test_risk_engine_evaluation_does_not_mutate_snapshot_or_context() -> None:
    snapshot = risk_snapshot()
    context = account_context(snapshot)
    snapshot_before = snapshot.model_dump_json()
    context_before = context.model_dump_json()

    RiskEngine(RiskConstitutionSettings()).evaluate(
        proposal(), snapshot, context, EVALUATED_AT
    )

    assert snapshot.model_dump_json() == snapshot_before
    assert context.model_dump_json() == context_before
