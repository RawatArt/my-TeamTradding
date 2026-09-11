from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from tests.fakes.agents import (
    entry_output,
    market_view,
    quant_developer_output,
    quant_output,
    skeptic_output,
    stage_one_context,
)
from tests.fakes.risk import CYCLE_ID, SNAPSHOT_ID

from ai_trading_team.schemas.enums import AgentRole
from ai_trading_team.schemas.orchestration import (
    AgentOutputReference,
    ChiefTraderInput,
    EntryAnalysisInput,
    PerformanceHistoryReference,
    PerformanceReviewInput,
    QuantDeveloperInput,
    SkepticInput,
)


def test_entry_input_accepts_only_trace_matched_stage_one_outputs() -> None:
    context = EntryAnalysisInput(
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        market=market_view(),
        stage_one=stage_one_context(),
    )
    payload = context.model_dump(mode="python")
    payload["stage_one"]["trend"]["cycle_id"] = "wrong-cycle"

    with pytest.raises(ValidationError, match="upstream output"):
        EntryAnalysisInput.model_validate(payload)


def test_quant_roles_can_be_omitted_or_receive_optional_upstream_evidence() -> None:
    developer = QuantDeveloperInput(
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        market=market_view(),
        stage_one=stage_one_context(),
        entry=entry_output(),
        quant_research=None,
    )
    skeptic = SkepticInput(
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        market=market_view(),
        stage_one=stage_one_context(),
        entry=entry_output(),
        quant_research=quant_output(),
        quant_developer=quant_developer_output(),
    )

    assert developer.quant_research is None
    assert skeptic.quant_research is not None
    assert skeptic.quant_developer is not None


def test_chief_context_requires_skeptic_but_allows_conditional_quant_absence() -> None:
    context = ChiefTraderInput(
        cycle_id=CYCLE_ID,
        snapshot_id=SNAPSHOT_ID,
        market=market_view(),
        stage_one=stage_one_context(),
        entry=entry_output(),
        skeptic=skeptic_output(),
    )

    assert context.quant_research is None
    assert context.quant_developer is None


def test_performance_review_input_is_retrospective_and_reference_based() -> None:
    history = PerformanceHistoryReference(
        history_id="history-001",
        schema_version="1.0.0",
        as_of=datetime(2026, 9, 11, tzinfo=UTC),
        record_count=20,
    )
    context = PerformanceReviewInput(
        cycle_id="review-cycle-001",
        snapshot_id="review-batch-001",
        performance_history=history,
        agent_output_refs=(
            AgentOutputReference(
                output_id="output-historical-001",
                cycle_id="historical-cycle-001",
                snapshot_id="historical-snapshot-001",
                agent_role=AgentRole.TREND_ANALYST,
                agent_version="1.0.0",
                prompt_version="1.0.0",
            ),
        ),
    )

    assert context.performance_history.record_count == 20
    assert "market" not in type(context).model_fields
