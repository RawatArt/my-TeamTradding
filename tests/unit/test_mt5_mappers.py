from datetime import UTC, datetime
from decimal import Decimal

import pytest
from tests.fakes.mt5 import account_record, symbol_record

from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory
from ai_trading_team.mt5.mappers import map_account_info, map_candle, map_symbol_info
from ai_trading_team.schemas.enums import Timeframe


def test_mapper_converts_float_inputs_through_decimal_strings() -> None:
    account = map_account_info(account_record(), datetime.now(UTC))

    assert account.balance == Decimal("50.0")
    assert isinstance(account.balance, Decimal)
    restored = type(account).model_validate_json(account.model_dump_json())
    assert isinstance(restored.balance, Decimal)


def test_mapper_rejects_missing_vendor_fields_with_structured_error() -> None:
    raw = symbol_record()
    del raw["trade_tick_size"]

    with pytest.raises(MT5ClientError) as caught:
        map_symbol_info(raw, datetime.now(UTC))

    assert caught.value.category is MT5ErrorCategory.DATA_MAPPING_ERROR
    assert caught.value.operation == "get_symbol_info"


def test_mapper_rejects_unknown_broker_enum_value() -> None:
    raw = account_record()
    raw["trade_mode"] = 999

    with pytest.raises(MT5ClientError) as caught:
        map_account_info(raw, datetime.now(UTC))

    assert caught.value.category is MT5ErrorCategory.DATA_MAPPING_ERROR


def test_mapper_rejects_impossible_candle_relationships() -> None:
    raw: dict[str, object] = {
        "time": 1_757_462_400,
        "open": 1.08,
        "high": 1.07,
        "low": 1.06,
        "close": 1.09,
        "tick_volume": 10,
        "spread": 2,
        "real_volume": 0,
    }

    with pytest.raises(MT5ClientError) as caught:
        map_candle(raw, "EURUSD.a", Timeframe.M15, datetime.now(UTC))

    assert caught.value.category is MT5ErrorCategory.DATA_MAPPING_ERROR
