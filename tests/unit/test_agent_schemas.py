import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

import pytest
from pydantic import ValidationError
from tests.fakes.agents import (
    chief_output,
    descriptor,
    entry_output,
    market_context_output,
    market_view,
    performance_output,
    price_action_output,
    quant_developer_output,
    quant_output,
    skeptic_output,
    trend_output,
)

from ai_trading_team.schemas.agents import (
    AgentDescriptor,
    AgentMarketView,
    AgentSymbolView,
    AgentWarning,
    ChiefTraderOutput,
    EntryAnalysisResult,
    TrendAnalysisOutput,
)
from ai_trading_team.schemas.enums import (
    AgentOutputStatus,
    AgentRole,
    EntryDisposition,
    TradeAction,
    TradeSide,
)


class TraceableAgentOutput(Protocol):
    cycle_id: str
    snapshot_id: str
    output_id: str
    produced_at: datetime


def test_agent_market_view_omits_sensitive_account_and_sizing_metadata() -> None:
    view = market_view()
    serialized = view.model_dump_json()

    assert "account" not in AgentMarketView.model_fields
    assert "open_positions" not in AgentMarketView.model_fields
    assert "account_id" not in serialized
    assert "Broker-Demo" not in serialized
    assert "trade_tick_value" not in AgentSymbolView.model_fields
    assert "trade_contract_size" not in AgentSymbolView.model_fields
    assert "volume_min" not in AgentSymbolView.model_fields
    assert "volume_max" not in AgentSymbolView.model_fields
    assert "volume_step" not in AgentSymbolView.model_fields


def test_market_view_preserves_decimal_and_utc_semantics() -> None:
    view = market_view()
    restored = AgentMarketView.model_validate_json(view.model_dump_json())

    assert isinstance(restored.tick.bid, Decimal)
    assert isinstance(restored.candles.h4[0].close, Decimal)
    assert restored.snapshot_completed_at.tzinfo is UTC
    assert restored.tick.source_time.tzinfo is UTC
    assert restored.candles.m15[0].open_time.tzinfo is UTC


def test_agent_output_is_immutable_traceable_and_decimal_safe() -> None:
    output = trend_output()
    payload = output.model_dump_json()
    decoded = json.loads(payload)
    restored = TrendAnalysisOutput.model_validate_json(payload)

    assert decoded["confidence"] == "0.50"
    assert isinstance(restored.confidence, Decimal)
    assert restored.produced_at.tzinfo is UTC
    with pytest.raises(ValidationError):
        output.confidence = Decimal("0.90")


@pytest.mark.parametrize(
    "factory",
    [
        market_context_output,
        trend_output,
        price_action_output,
        entry_output,
        quant_output,
        quant_developer_output,
        skeptic_output,
        chief_output,
        performance_output,
    ],
)
def test_all_nine_role_outputs_use_the_traceable_envelope(
    factory: Callable[[], TraceableAgentOutput],
) -> None:
    output = factory()

    assert output.cycle_id
    assert output.snapshot_id
    assert output.output_id
    assert output.produced_at.tzinfo is UTC


def test_degraded_output_requires_an_explicit_warning() -> None:
    payload = trend_output().model_dump(mode="python")
    payload["status"] = AgentOutputStatus.DEGRADED

    with pytest.raises(ValidationError, match="warning"):
        TrendAnalysisOutput.model_validate(payload)

    payload["warnings"] = (
        AgentWarning(code="missing-optional-input", message="Optional input unavailable"),
    )
    assert TrendAnalysisOutput.model_validate(payload).status is AgentOutputStatus.DEGRADED


def test_output_rejects_naive_time_and_wrong_role() -> None:
    payload = trend_output().model_dump(mode="python")
    payload["produced_at"] = datetime(2026, 9, 11)
    payload["agent_role"] = AgentRole.SKEPTIC

    with pytest.raises(ValidationError):
        TrendAnalysisOutput.model_validate(payload)


def test_descriptor_retains_vendor_neutral_policy_references() -> None:
    configured = descriptor(AgentRole.TREND_ANALYST)

    assert configured.runtime_profile_ref == "runtime-unassigned"
    assert configured.invocation_policy_ref == "invocation-default"
    assert configured.cost_policy_ref == "cost-policy-unassigned"
    assert "model" not in AgentDescriptor.model_fields
    assert "provider" not in AgentDescriptor.model_fields


def test_descriptor_rejects_incompatible_invocation_mode() -> None:
    payload = descriptor(AgentRole.TREND_ANALYST).model_dump(mode="python")
    payload["invocation_mode"] = "OFFLINE"

    with pytest.raises(ValidationError, match="incompatible"):
        AgentDescriptor.model_validate(payload)


def test_no_entry_cannot_smuggle_a_directional_candidate() -> None:
    with pytest.raises(ValidationError, match="NO_ENTRY"):
        EntryAnalysisResult(
            disposition=EntryDisposition.NO_ENTRY,
            side=TradeSide.BUY,
            entry=Decimal("1.0"),
            rationale="Invalid candidate",
        )


def test_enter_now_requires_side_entry_and_stop() -> None:
    with pytest.raises(ValidationError, match="ENTER_NOW"):
        EntryAnalysisResult(
            disposition=EntryDisposition.ENTER_NOW,
            rationale="Missing mandatory candidate fields",
        )


def test_chief_hold_forbids_trade_proposal() -> None:
    hold = chief_output()
    payload = hold.model_dump(mode="python")
    payload["payload"]["trade_proposal"] = chief_output(TradeAction.BUY).payload.trade_proposal

    with pytest.raises(ValidationError, match="HOLD"):
        ChiefTraderOutput.model_validate(payload)


def test_chief_buy_requires_trace_matched_proposal() -> None:
    buy = chief_output(TradeAction.BUY)
    assert buy.payload.trade_proposal is not None
    payload = buy.model_dump(mode="python")
    payload["payload"]["trade_proposal"]["snapshot_id"] = "another-snapshot"

    with pytest.raises(ValidationError, match="cycle and snapshot"):
        ChiefTraderOutput.model_validate(payload)


def test_performance_review_cannot_authorize_automatic_strategy_change() -> None:
    output = performance_output()
    payload = output.model_dump(mode="python")
    payload["payload"]["automatic_strategy_change_permitted"] = True

    with pytest.raises(ValidationError):
        type(output).model_validate(payload)


def test_role_output_payloads_are_strict() -> None:
    payload = entry_output().model_dump(mode="python")
    payload["payload"]["position_size"] = "100"

    with pytest.raises(ValidationError):
        type(entry_output()).model_validate(payload)
