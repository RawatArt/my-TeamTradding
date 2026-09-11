import pytest
from pydantic import ValidationError

from ai_trading_team.config import AppSettings, FeatureEngineSettings


def test_feature_settings_have_versioned_conservative_defaults() -> None:
    settings = FeatureEngineSettings()

    assert settings.configuration_version == "1.0.0"
    assert settings.recent_range_lookback == 20
    assert settings.swing_left_bars == 2
    assert settings.swing_right_bars == 2
    assert AppSettings().features == settings


@pytest.mark.parametrize(
    ("field", "value"),
    (("recent_range_lookback", 0), ("swing_left_bars", 0), ("swing_right_bars", 0)),
)
def test_feature_settings_reject_non_positive_windows(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        FeatureEngineSettings.model_validate({field: value})
