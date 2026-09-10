from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_trading_team.config.settings import AppSettings, RiskConstitutionSettings
from ai_trading_team.schemas.enums import ApplicationMode


def test_settings_default_to_shadow_with_live_flags_disabled() -> None:
    settings = AppSettings()

    assert settings.app_mode is ApplicationMode.SHADOW
    assert settings.enable_live_trading is False
    assert settings.live_trading_acknowledged is False


def test_default_risk_constitution_matches_master_specification() -> None:
    risk = RiskConstitutionSettings()

    assert risk.starting_balance == Decimal("50")
    assert risk.minimum_risk_percent == Decimal("0.25")
    assert risk.normal_risk_percent == Decimal("0.50")
    assert risk.maximum_risk_percent == Decimal("1.00")
    assert risk.maximum_daily_loss_percent == Decimal("3")
    assert risk.drawdown_warning_percent == Decimal("5")
    assert risk.drawdown_safe_mode_percent == Decimal("8")
    assert risk.drawdown_stop_percent == Decimal("15")
    assert risk.minimum_risk_reward == Decimal("1.50")
    assert risk.maximum_open_positions == 1
    assert risk.stop_loss_required is True


def test_risk_decimal_values_survive_json_round_trip_without_binary_float() -> None:
    risk = RiskConstitutionSettings.model_validate(
        {"normal_risk_percent": "0.50", "minimum_risk_reward": "1.50"}
    )

    python_data = risk.model_dump()
    assert isinstance(python_data["normal_risk_percent"], Decimal)

    json_text = risk.model_dump_json()
    assert '"normal_risk_percent":"0.50"' in json_text

    restored = RiskConstitutionSettings.model_validate_json(json_text)
    assert restored.normal_risk_percent == Decimal("0.50")
    assert isinstance(restored.normal_risk_percent, Decimal)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"minimum_risk_percent": "0.75", "normal_risk_percent": "0.50"}, "risk percentages"),
        (
            {"drawdown_warning_percent": "8", "drawdown_safe_mode_percent": "8"},
            "drawdown thresholds",
        ),
        ({"stop_loss_required": False}, "stop loss is mandatory"),
        ({"martingale_enabled": True}, "martingale is forbidden"),
        ({"averaging_down_enabled": True}, "averaging down is forbidden"),
        ({"revenge_trading_enabled": True}, "revenge trading is forbidden"),
        ({"maximum_risk_percent": "1.01"}, "less than or equal to 1"),
    ],
)
def test_invalid_risk_constitution_is_rejected(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RiskConstitutionSettings.model_validate(override)


def test_blank_configured_symbol_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AppSettings.model_validate({"trading_symbol": "   "})
