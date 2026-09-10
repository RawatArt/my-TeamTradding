import pytest
from pydantic import ValidationError

from ai_trading_team.config import AppSettings, MarketDataSettings


def test_market_data_defaults_are_bounded_and_explicit() -> None:
    settings = MarketDataSettings()

    assert settings.m15_candle_count == 200
    assert settings.h1_candle_count == 200
    assert settings.h4_candle_count == 200
    assert settings.max_tick_age_seconds == 120


def test_market_data_settings_load_from_nested_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_DATA__M15_CANDLE_COUNT", "42")
    monkeypatch.setenv("MARKET_DATA__MAX_TICK_AGE_SECONDS", "300")

    settings = AppSettings()

    assert settings.market_data.m15_candle_count == 42
    assert settings.market_data.max_tick_age_seconds == 300


def test_market_data_candle_count_must_match_m1_bounds() -> None:
    try:
        MarketDataSettings(m15_candle_count=5_001)
    except ValidationError:
        pass
    else:
        raise AssertionError("candle counts above the M1 maximum must be rejected")
