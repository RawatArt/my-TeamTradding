import inspect
from decimal import Decimal
from pathlib import Path

from tests.fakes.agents import chief_output
from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot

from ai_trading_team.agents import BaseAgent
from ai_trading_team.agents.roles import (
    ChiefTraderAgent,
    EntryAnalyst,
    MarketContextAgent,
    PerformanceReviewer,
    PriceActionAnalyst,
    QuantResearcher,
    SeniorQuantDeveloper,
    SkepticAgent,
    TrendAnalyst,
)
from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.orchestration import AgentFailurePolicy
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.agents import (
    AgentDescriptor,
    AgentMarketView,
    ChiefTraderOutput,
    EntryAnalysisResult,
)
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import (
    AgentFailureCategory,
    FailureDisposition,
    RiskDecisionStatus,
    TradeAction,
)


def test_agents_package_has_no_mt5_risk_execution_or_model_vendor_import() -> None:
    source_root = Path(__file__).parents[2] / "src" / "ai_trading_team" / "agents"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))
    normalized = source.casefold()

    forbidden = (
        "ai_trading_team.mt5",
        "ai_trading_team.risk",
        "ai_trading_team.execution",
        "import openai",
        "import anthropic",
        "import gemini",
        "order_send",
        "symbol_select",
    )
    for identifier in forbidden:
        assert identifier not in normalized


def test_agent_contracts_have_no_other_agent_or_service_reference() -> None:
    contracts = (
        MarketContextAgent,
        TrendAnalyst,
        PriceActionAnalyst,
        EntryAnalyst,
        QuantResearcher,
        SeniorQuantDeveloper,
        SkepticAgent,
        ChiefTraderAgent,
        PerformanceReviewer,
    )

    assert {
        name
        for name, member in inspect.getmembers(BaseAgent, predicate=inspect.isfunction)
        if not name.startswith("_")
    } == {"analyze"}
    assert all(not hasattr(contract, "agents") for contract in contracts)
    assert all(not hasattr(contract, "mt5") for contract in contracts)
    assert all(not hasattr(contract, "risk_engine") for contract in contracts)


def test_agent_market_view_excludes_account_and_position_identity() -> None:
    assert "account" not in AgentMarketView.model_fields
    assert "open_positions" not in AgentMarketView.model_fields
    assert "account_id" not in AgentMarketView.model_fields
    assert "server" not in AgentMarketView.model_fields


def test_agent_contracts_have_no_position_size_or_order_request() -> None:
    assert "position_size" not in EntryAnalysisResult.model_fields
    assert "volume" not in EntryAnalysisResult.model_fields
    assert "order" not in EntryAnalysisResult.model_fields
    assert "order_request" not in ChiefTraderOutput.model_fields
    assert "selected_volume" not in ChiefTraderOutput.model_fields


def test_malformed_agent_output_deterministically_results_in_hold() -> None:
    assert (
        AgentFailurePolicy.resolve(AgentFailureCategory.INVALID_OUTPUT)
        is FailureDisposition.HOLD
    )


def test_chief_buy_cannot_override_existing_deterministic_risk_engine() -> None:
    snapshot = risk_snapshot()
    chief = chief_output(TradeAction.BUY)
    assert chief.payload.trade_proposal is not None
    proposal_payload = chief.payload.trade_proposal.model_dump(mode="python")
    proposal_payload["stop_loss"] = None
    unsafe_proposal = TradeProposal.model_validate(proposal_payload)

    decision = RiskEngine(RiskConstitutionSettings()).evaluate(
        unsafe_proposal,
        snapshot,
        account_context(snapshot),
        EVALUATED_AT,
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.position_sizing is None


def test_agent_descriptor_has_references_not_credentials_or_provider_configuration() -> None:
    fields = AgentDescriptor.model_fields

    assert "runtime_profile_ref" in fields
    assert "invocation_policy_ref" in fields
    assert "cost_policy_ref" in fields
    assert "api_key" not in fields
    assert "password" not in fields
    assert "provider" not in fields
    assert "model_name" not in fields


def test_agent_output_confidence_is_decimal_but_not_a_risk_input() -> None:
    output = chief_output()

    assert isinstance(output.confidence, Decimal)
    assert "confidence" not in inspect.signature(RiskEngine.evaluate).parameters
