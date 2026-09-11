from decimal import Decimal

from ai_trading_team.features.indicators import ema_series


def test_ema_uses_arithmetic_seed_and_recursive_definition() -> None:
    result = ema_series(tuple(Decimal(value) for value in (1, 2, 3, 4, 5)), 3)

    assert result == (None, None, Decimal("2"), Decimal("3"), Decimal("4"))


def test_ema20_50_200_known_constant_vectors() -> None:
    values = (Decimal("1.23450"),) * 200

    assert ema_series(values, 20)[-1] == Decimal("1.23450")
    assert ema_series(values, 50)[-1] == Decimal("1.23450")
    assert ema_series(values, 200)[-1] == Decimal("1.23450")


def test_ema_does_not_fabricate_insufficient_history() -> None:
    assert ema_series((Decimal("1"), Decimal("2")), 3) == (None, None)

