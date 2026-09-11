import inspect

from ai_trading_team.risk import PositionSizer, RiskEngine
from ai_trading_team.schemas.agents import AgentOutput
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.risk import AccountRiskContext, PositionSizingResult, RiskDecision


def test_confidence_exists_only_on_agent_output_side_of_risk_boundary() -> None:
    assert "confidence" in AgentOutput.model_fields
    assert "confidence" not in TradeProposal.model_fields
    assert "confidence" not in AccountRiskContext.model_fields
    assert "confidence" not in PositionSizingResult.model_fields
    assert "confidence" not in RiskDecision.model_fields
    assert "confidence" not in inspect.signature(PositionSizer.calculate).parameters
    assert "confidence" not in inspect.signature(RiskEngine.evaluate).parameters
