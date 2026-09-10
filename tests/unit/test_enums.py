from ai_trading_team.schemas.enums import ApplicationMode, RiskState


def test_application_mode_and_risk_state_are_separate_concepts() -> None:
    assert ApplicationMode.SHADOW.value == "SHADOW"
    assert RiskState.SAFE_MODE.value == "SAFE_MODE"
    assert set(ApplicationMode) == {
        ApplicationMode.BACKTEST,
        ApplicationMode.SHADOW,
        ApplicationMode.DEMO,
        ApplicationMode.LIVE,
    }
    assert set(RiskState) == {
        RiskState.NORMAL,
        RiskState.CAUTION,
        RiskState.SAFE_MODE,
        RiskState.HALTED,
    }


def test_live_remains_a_valid_core_application_mode() -> None:
    assert ApplicationMode("LIVE") is ApplicationMode.LIVE

