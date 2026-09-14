"""Non-negotiable M10 qualification safety boundaries."""

from pathlib import Path

import pytest

from ai_trading_team.config import (
    AppSettings,
    ContinuousShadowSettings,
    QualificationSettings,
)
from ai_trading_team.config.startup import StartupPolicyError, validate_m10_startup
from ai_trading_team.schemas.enums import ApplicationMode, GraduationDisposition
from ai_trading_team.schemas.qualification import (
    QualificationPerformanceReviewInput,
    ShadowGraduationEvaluation,
)


@pytest.mark.parametrize("mode", [ApplicationMode.DEMO, ApplicationMode.LIVE])
def test_m10_startup_prohibits_demo_and_live(mode: ApplicationMode) -> None:
    with pytest.raises(StartupPolicyError):
        validate_m10_startup(AppSettings(app_mode=mode))


def test_qualification_cannot_run_with_the_m9_runtime() -> None:
    with pytest.raises(StartupPolicyError, match="separate explicit tasks"):
        validate_m10_startup(
            AppSettings(
                app_mode=ApplicationMode.SHADOW,
                continuous_shadow=ContinuousShadowSettings(enabled=True),
                qualification=QualificationSettings(enabled=True),
            )
        )


def test_qualification_source_has_no_execution_runtime_or_provider_capability() -> None:
    root = Path("src/ai_trading_team/qualification")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "order_send",
        "symbol_select",
        "position_close",
        "position_modify",
        "MetaTrader5",
        "ContinuousShadowRuntime",
        "RuntimeRouter",
        "RiskEngine(",
        "openai",
        "anthropic",
        "google.genai",
    )
    assert all(token not in source for token in forbidden)


def test_graduation_contract_cannot_enable_a_trading_mode() -> None:
    schema = str(ShadowGraduationEvaluation.model_json_schema()).casefold()
    assert "enable_demo" not in schema
    assert "enable_live" not in schema
    assert "order_request" not in schema
    assert set(GraduationDisposition) == {
        GraduationDisposition.ELIGIBLE_FOR_DEMO_REVIEW,
        GraduationDisposition.NOT_ELIGIBLE,
    }


def test_performance_review_is_advisory_only() -> None:
    schema = QualificationPerformanceReviewInput.model_json_schema()
    properties = schema["properties"]
    for field in (
        "automatic_strategy_change_permitted",
        "threshold_change_permitted",
        "mode_change_permitted",
    ):
        assert properties[field]["const"] is False
