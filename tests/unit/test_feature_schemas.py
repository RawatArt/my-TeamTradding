from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.fakes.features import feature_snapshot

from ai_trading_team.features import MarketFeatureEngine
from ai_trading_team.schemas.enums import FeatureAvailability, FeatureUnit
from ai_trading_team.schemas.features import DecimalFeatureValue


def test_invalid_input_is_not_a_per_feature_availability_state() -> None:
    assert tuple(FeatureAvailability) == (
        FeatureAvailability.VALID,
        FeatureAvailability.INSUFFICIENT_HISTORY,
        FeatureAvailability.UNAVAILABLE,
    )


def test_feature_value_requires_value_only_when_valid() -> None:
    valid = DecimalFeatureValue(
        status=FeatureAvailability.VALID,
        unit=FeatureUnit.PRICE,
        value=Decimal("1.2"),
        required_candles=20,
        available_candles=20,
    )
    assert isinstance(valid.value, Decimal)

    with pytest.raises(ValidationError):
        valid.model_copy(update={"value": None}).__class__.model_validate(
            valid.model_copy(update={"value": None}).model_dump()
        )


def test_market_feature_set_is_immutable() -> None:
    feature_set = MarketFeatureEngine().calculate(feature_snapshot())

    with pytest.raises(ValidationError):
        feature_set.symbol = "OTHER"
