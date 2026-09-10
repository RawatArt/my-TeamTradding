import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_trading_team.schemas.agents import AgentOutput
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import Timeframe, TradeAction, TradeSide
from ai_trading_team.schemas.market import MarketQuote


def quote_payload() -> dict[str, object]:
    return {
        "cycle_id": "EURUSD:M15:2026-09-10T00:00:00Z",
        "schema_version": "1.0.0",
        "timestamp": "2026-09-10T07:00:00+07:00",
        "symbol": "EURUSD.a",
        "timeframe": "M15",
        "bid": "1.08123",
        "ask": "1.08135",
        "spread": "0.00012",
    }


def test_traceable_record_requires_cycle_id_and_normalizes_timestamp_to_utc() -> None:
    quote = MarketQuote.model_validate(quote_payload())

    assert quote.cycle_id == "EURUSD:M15:2026-09-10T00:00:00Z"
    assert quote.schema_version == "1.0.0"
    assert quote.timestamp == datetime(2026, 9, 10, tzinfo=UTC)
    assert quote.timestamp.utcoffset() == timedelta(0)


def test_traceable_record_rejects_naive_timestamp() -> None:
    payload = quote_payload()
    payload["timestamp"] = datetime(2026, 9, 10)

    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketQuote.model_validate(payload)


def test_market_quote_validates_exact_spread_and_uses_decimal_midpoint() -> None:
    quote = MarketQuote.model_validate(quote_payload())

    assert quote.mid == Decimal("1.08129")
    assert isinstance(quote.mid, Decimal)

    invalid = quote_payload()
    invalid["spread"] = "0.00013"
    with pytest.raises(ValidationError, match="spread must equal"):
        MarketQuote.model_validate(invalid)


def test_decimal_values_remain_decimal_through_python_and_json_boundaries() -> None:
    quote = MarketQuote.model_validate(quote_payload())

    python_data = quote.model_dump()
    assert isinstance(python_data["bid"], Decimal)
    assert isinstance(python_data["ask"], Decimal)
    assert isinstance(python_data["spread"], Decimal)

    json_text = quote.model_dump_json()
    json_data = json.loads(json_text)
    assert json_data["bid"] == "1.08123"
    assert isinstance(json_data["bid"], str)

    restored = MarketQuote.model_validate_json(json_text)
    assert restored.bid == Decimal("1.08123")
    assert isinstance(restored.bid, Decimal)


def test_agent_output_is_traceable_and_confidence_is_decimal() -> None:
    output = AgentOutput.model_validate(
        {
            "cycle_id": "cycle-001",
            "timestamp": datetime.now(UTC),
            "agent": "trend_analyst",
            "agent_version": "1.0.0",
            "decision": TradeAction.HOLD,
            "confidence": "0.72",
            "evidence": ("Completed H1 candle only",),
        }
    )

    assert output.confidence == Decimal("0.72")
    assert isinstance(output.confidence, Decimal)
    assert output.cycle_id == "cycle-001"


def test_agent_confidence_outside_closed_unit_interval_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentOutput.model_validate(
            {
                "cycle_id": "cycle-001",
                "timestamp": datetime.now(UTC),
                "agent": "trend_analyst",
                "agent_version": "1.0.0",
                "decision": TradeAction.HOLD,
                "confidence": "1.01",
            }
        )


def test_trade_proposal_is_cycle_and_snapshot_traceable() -> None:
    timestamp = datetime.now(UTC)
    proposal = TradeProposal.model_validate(
        {
            "cycle_id": "cycle-002",
            "schema_version": "1.0.0",
            "timestamp": timestamp,
            "proposal_id": "proposal-002",
            "snapshot_id": "snapshot-002",
            "symbol": "XAUUSDm",
            "side": TradeSide.BUY,
            "entry": "2400.10",
            "stop_loss": "2390.10",
            "take_profit": "2420.10",
            "rationale": "Boundary-contract test only",
        }
    )
    assert proposal.cycle_id == "cycle-002"
    assert proposal.snapshot_id == "snapshot-002"
    assert proposal.schema_version == "1.0.0"
    assert isinstance(proposal.entry, Decimal)
    assert "position_size" not in TradeProposal.model_fields


def test_market_quote_does_not_assume_a_broker_symbol_name() -> None:
    payload = quote_payload()
    payload["symbol"] = "US30.cash#"

    quote = MarketQuote.model_validate(payload)

    assert quote.symbol == "US30.cash#"
    assert quote.timeframe is Timeframe.M15
