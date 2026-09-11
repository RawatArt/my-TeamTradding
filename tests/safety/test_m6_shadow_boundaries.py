import asyncio
import inspect
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from tests.fakes.risk import EVALUATED_AT, account_context, risk_snapshot
from tests.fakes.shadow import ScriptedShadowInvoker

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.orchestration.shadow import ShadowCycleOrchestrator
from ai_trading_team.risk import RiskEngine
from ai_trading_team.schemas.common import CoreModel
from ai_trading_team.schemas.enums import AgentRole, ShadowExecutionStatus, TradeAction
from ai_trading_team.schemas.risk import RiskDecision
from ai_trading_team.storage.shadow_audit import InMemoryShadowAuditRepository


class ConfidenceInvoker(ScriptedShadowInvoker):
    def __init__(self, confidence: Decimal) -> None:
        super().__init__(chief_action=TradeAction.BUY)
        self._confidence = confidence

    def _output(self, role: AgentRole) -> CoreModel:
        output = super()._output(role)
        if hasattr(output, "confidence"):
            return output.model_copy(update={"confidence": self._confidence})
        return output


def approved_risk_with_confidence(confidence: Decimal) -> RiskDecision:
    snapshot = risk_snapshot()
    orchestrator = ShadowCycleOrchestrator(
        invoker=ConfidenceInvoker(confidence),
        risk_engine=RiskEngine(RiskConstitutionSettings()),
        repository=InMemoryShadowAuditRepository(),
        clock=lambda: EVALUATED_AT + timedelta(seconds=30),
    )
    record = asyncio.run(
        orchestrator.run_shadow_cycle(snapshot, account_context(snapshot))
    )
    assert record.shadow_trade_intent is not None
    return record.shadow_trade_intent.risk_decision


def test_agent_confidence_cannot_change_m3_position_size() -> None:
    low = approved_risk_with_confidence(Decimal("0.01"))
    high = approved_risk_with_confidence(Decimal("0.99"))

    assert low.position_sizing == high.position_sizing
    assert low.account_metrics == high.account_metrics


def test_shadow_intent_has_only_non_execution_status() -> None:
    assert tuple(ShadowExecutionStatus) == (ShadowExecutionStatus.NOT_EXECUTED_SHADOW,)


def test_m6_modules_have_no_mt5_or_execution_dependency() -> None:
    import ai_trading_team.orchestration.context as context_module
    import ai_trading_team.orchestration.runtime as runtime_module
    import ai_trading_team.orchestration.shadow as shadow_module

    source = "\n".join(
        inspect.getsource(module)
        for module in (context_module, runtime_module, shadow_module)
    ).casefold()
    assert "metatrader5" not in source
    assert "ai_trading_team.mt5" not in source
    assert "ai_trading_team.execution" not in source


def test_production_has_no_broker_mutation_identifiers() -> None:
    root = Path(__file__).parents[2] / "src" / "ai_trading_team"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    forbidden = (
        "order_send",
        "symbol_select",
        "position_modify",
        "position_close",
        "order_place",
    )
    assert all(identifier not in source for identifier in forbidden)
