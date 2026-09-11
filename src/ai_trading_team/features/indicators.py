"""Transparent Decimal-only rolling indicator definitions for M7."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from decimal import Context, Decimal, localcontext

from ai_trading_team.features.definitions import DECIMAL_PRECISION, DECIMAL_ROUNDING
from ai_trading_team.schemas.mt5 import MT5Candle

_HUNDRED = Decimal("100")


def ema_series(values: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
    """Return EMA values seeded by the arithmetic mean of the first ``period`` values."""
    _require_period(period)
    result: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    with _context():
        period_decimal = Decimal(period)
        alpha = Decimal(2) / Decimal(period + 1)
        current = sum(values[:period], start=Decimal(0)) / period_decimal
        result[period - 1] = +current
        for index in range(period, len(values)):
            current = alpha * values[index] + (Decimal(1) - alpha) * current
            result[index] = +current
    return tuple(result)


def rsi_series(values: Sequence[Decimal], period: int = 14) -> tuple[Decimal | None, ...]:
    """Return Wilder RSI, requiring ``period + 1`` closes for the first value."""
    _require_period(period)
    result: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return tuple(result)
    with _context():
        changes = tuple(values[index] - values[index - 1] for index in range(1, len(values)))
        gains = tuple(max(change, Decimal(0)) for change in changes)
        losses = tuple(max(-change, Decimal(0)) for change in changes)
        period_decimal = Decimal(period)
        average_gain = sum(gains[:period], start=Decimal(0)) / period_decimal
        average_loss = sum(losses[:period], start=Decimal(0)) / period_decimal
        result[period] = _rsi(average_gain, average_loss)
        for change_index in range(period, len(changes)):
            average_gain = (
                average_gain * Decimal(period - 1) + gains[change_index]
            ) / period_decimal
            average_loss = (
                average_loss * Decimal(period - 1) + losses[change_index]
            ) / period_decimal
            result[change_index + 1] = _rsi(average_gain, average_loss)
    return tuple(result)


def atr_series(
    candles: Sequence[MT5Candle], period: int = 14
) -> tuple[Decimal | None, ...]:
    """Return Wilder ATR without guessing a close before the supplied candle window."""
    _require_period(period)
    result: list[Decimal | None] = [None] * len(candles)
    if len(candles) <= period:
        return tuple(result)
    with _context():
        true_ranges = tuple(
            _true_range(candles[index], candles[index - 1].close)
            for index in range(1, len(candles))
        )
        period_decimal = Decimal(period)
        current = sum(true_ranges[:period], start=Decimal(0)) / period_decimal
        result[period] = +current
        for range_index in range(period, len(true_ranges)):
            current = (
                current * Decimal(period - 1) + true_ranges[range_index]
            ) / period_decimal
            result[range_index + 1] = +current
    return tuple(result)


def adx_series(
    candles: Sequence[MT5Candle], period: int = 14
) -> tuple[Decimal | None, ...]:
    """Return Wilder ADX; the first value is available after ``2 * period`` candles."""
    _require_period(period)
    result: list[Decimal | None] = [None] * len(candles)
    if len(candles) < period * 2:
        return tuple(result)
    with _context():
        true_ranges: list[Decimal] = []
        positive_dm: list[Decimal] = []
        negative_dm: list[Decimal] = []
        for index in range(1, len(candles)):
            current = candles[index]
            previous = candles[index - 1]
            true_ranges.append(_true_range(current, previous.close))
            up_move = current.high - previous.high
            down_move = previous.low - current.low
            positive_dm.append(
                up_move if up_move > down_move and up_move > 0 else Decimal(0)
            )
            negative_dm.append(
                down_move if down_move > up_move and down_move > 0 else Decimal(0)
            )

        smoothed_tr = sum(true_ranges[:period], start=Decimal(0))
        smoothed_positive = sum(positive_dm[:period], start=Decimal(0))
        smoothed_negative = sum(negative_dm[:period], start=Decimal(0))
        dx_values = [
            _directional_index(smoothed_tr, smoothed_positive, smoothed_negative)
        ]
        current_adx: Decimal | None = None
        period_decimal = Decimal(period)
        for transition_index in range(period, len(true_ranges)):
            smoothed_tr = (
                smoothed_tr
                - smoothed_tr / period_decimal
                + true_ranges[transition_index]
            )
            smoothed_positive = (
                smoothed_positive
                - smoothed_positive / period_decimal
                + positive_dm[transition_index]
            )
            smoothed_negative = (
                smoothed_negative
                - smoothed_negative / period_decimal
                + negative_dm[transition_index]
            )
            dx = _directional_index(
                smoothed_tr,
                smoothed_positive,
                smoothed_negative,
            )
            dx_values.append(dx)
            candle_index = transition_index + 1
            if len(dx_values) == period:
                current_adx = sum(dx_values, start=Decimal(0)) / period_decimal
                result[candle_index] = +current_adx
            elif len(dx_values) > period:
                if current_adx is None:
                    raise RuntimeError("ADX smoothing state is unexpectedly unavailable")
                current_adx = (
                    current_adx * Decimal(period - 1) + dx
                ) / period_decimal
                result[candle_index] = +current_adx
    return tuple(result)


def _true_range(candle: MT5Candle, previous_close: Decimal) -> Decimal:
    return max(
        candle.high - candle.low,
        abs(candle.high - previous_close),
        abs(candle.low - previous_close),
    )


def _rsi(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_loss == 0:
        return Decimal(50) if average_gain == 0 else _HUNDRED
    relative_strength = average_gain / average_loss
    return _HUNDRED - _HUNDRED / (Decimal(1) + relative_strength)


def _directional_index(
    smoothed_tr: Decimal,
    smoothed_positive: Decimal,
    smoothed_negative: Decimal,
) -> Decimal:
    if smoothed_tr == 0:
        return Decimal(0)
    positive_di = _HUNDRED * smoothed_positive / smoothed_tr
    negative_di = _HUNDRED * smoothed_negative / smoothed_tr
    denominator = positive_di + negative_di
    if denominator == 0:
        return Decimal(0)
    return _HUNDRED * abs(positive_di - negative_di) / denominator


def _require_period(period: int) -> None:
    if period <= 0:
        raise ValueError("indicator period must be positive")


@contextmanager
def _context() -> Iterator[Context]:
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)) as context:
        yield context
