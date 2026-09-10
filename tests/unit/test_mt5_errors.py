from ai_trading_team.mt5.errors import MT5ClientError, MT5ErrorCategory


def test_mt5_error_exposes_structured_category_operation_and_code() -> None:
    error = MT5ClientError(
        MT5ErrorCategory.TICK_ERROR,
        "get_tick",
        "current tick is unavailable",
        vendor_code=-4,
    )

    assert error.category is MT5ErrorCategory.TICK_ERROR
    assert error.operation == "get_tick"
    assert error.vendor_code == -4
    assert "vendor_code=-4" in str(error)
