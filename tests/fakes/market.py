"""Typed fake observations for M2 snapshot tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.schemas.enums import (
    BrokerAccountMode,
    BrokerPositionSide,
    SymbolTradeMode,
    Timeframe,
)
from ai_trading_team.schemas.mt5 import (
    MT5AccountInfo,
    MT5Candle,
    MT5OpenPosition,
    MT5SymbolInfo,
    MT5Tick,
)
from ai_trading_team.schemas.timeframes import timeframe_duration

SNAPSHOT_START = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
SNAPSHOT_END = SNAPSHOT_START + timedelta(seconds=5)
SYMBOL = "EURUSD.a"


def symbol_info(*, symbol: str = SYMBOL) -> MT5SymbolInfo:
    return MT5SymbolInfo(
        retrieved_at=SNAPSHOT_START + timedelta(seconds=1),
        symbol=symbol,
        description="Euro vs US Dollar",
        path="Forex\\Majors",
        selected=True,
        visible=True,
        digits=5,
        point=Decimal("0.00001"),
        trade_tick_size=Decimal("0.00001"),
        trade_tick_value=Decimal("1.00"),
        trade_contract_size=Decimal("100000"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        trade_stops_level=20,
        trade_freeze_level=10,
        currency_base="EUR",
        currency_profit="USD",
        trading_mode=SymbolTradeMode.FULL,
    )


def account_info(*, retrieved_at: datetime | None = None) -> MT5AccountInfo:
    return MT5AccountInfo(
        retrieved_at=retrieved_at or SNAPSHOT_START + timedelta(seconds=1),
        account_id=12345678,
        trade_mode=BrokerAccountMode.DEMO,
        leverage=100,
        limit_orders=200,
        margin_stop_out_mode=0,
        trade_allowed=True,
        expert_trading_allowed=True,
        margin_mode=2,
        currency_digits=2,
        fifo_close=False,
        balance=Decimal("50.00"),
        credit=Decimal("0"),
        profit=Decimal("0.05"),
        equity=Decimal("50.05"),
        margin=Decimal("1.25"),
        margin_free=Decimal("48.80"),
        margin_level=Decimal("4004"),
        margin_stop_out_call=Decimal("50"),
        margin_stop_out_stop=Decimal("30"),
        margin_initial=Decimal("0"),
        margin_maintenance=Decimal("0"),
        assets=Decimal("0"),
        liabilities=Decimal("0"),
        commission_blocked=Decimal("0"),
        currency="USD",
        server="Broker-Demo",
        company="Broker",
    )


def tick(*, source_time: datetime | None = None, symbol: str = SYMBOL) -> MT5Tick:
    return MT5Tick(
        retrieved_at=SNAPSHOT_START + timedelta(seconds=4),
        symbol=symbol,
        source_time=source_time or SNAPSHOT_START + timedelta(seconds=3),
        bid=Decimal("1.08123"),
        ask=Decimal("1.08135"),
        spread=Decimal("0.00012"),
        last=Decimal("1.08130"),
        volume=Decimal("3.5"),
        flags=6,
    )


def candles(
    timeframe: Timeframe,
    count: int = 2,
    *,
    latest_close: datetime | None = None,
    symbol: str = SYMBOL,
) -> tuple[MT5Candle, ...]:
    duration = timeframe_duration(timeframe)
    final_close = latest_close or SNAPSHOT_START
    first_open = final_close - duration * count
    retrieved_at = SNAPSHOT_START + timedelta(seconds=2)
    return tuple(
        MT5Candle(
            retrieved_at=retrieved_at,
            symbol=symbol,
            timeframe=timeframe,
            open_time=first_open + duration * index,
            open=Decimal("1.08000"),
            high=Decimal("1.09000"),
            low=Decimal("1.07000"),
            close=Decimal("1.08500"),
            tick_volume=123,
            broker_spread_points=12,
            real_volume=5,
        )
        for index in range(count)
    )


def position(*, symbol: str = SYMBOL, ticket: int = 101) -> MT5OpenPosition:
    return MT5OpenPosition(
        retrieved_at=SNAPSHOT_START + timedelta(seconds=3),
        ticket=ticket,
        identifier=ticket + 100,
        symbol=symbol,
        side=BrokerPositionSide.BUY,
        volume=Decimal("0.01"),
        open_time=SNAPSHOT_START - timedelta(hours=2),
        update_time=SNAPSHOT_START - timedelta(minutes=1),
        price_open=Decimal("1.08000"),
        stop_loss=Decimal("1.07000"),
        take_profit=Decimal("1.10000"),
        price_current=Decimal("1.08500"),
        swap=Decimal("-0.01"),
        profit=Decimal("0.05"),
        magic=0,
        reason=0,
        comment="manual demo position",
        external_id="",
    )


class FakeMarketDataSource:
    """Controllable fake matching the M2 read-only protocol."""

    def __init__(self) -> None:
        self.symbol_info_result = symbol_info()
        self.account_result = account_info()
        self.tick_result = tick()
        self.candle_results = {
            Timeframe.M15: candles(Timeframe.M15),
            Timeframe.H1: candles(Timeframe.H1),
            Timeframe.H4: candles(Timeframe.H4),
        }
        self.positions_result: tuple[MT5OpenPosition, ...] = (position(),)
        self.symbol_info_calls: list[str] = []
        self.candle_calls: list[tuple[str, Timeframe, int, bool]] = []
        self.position_calls: list[str | None] = []

    def get_account_info(self) -> MT5AccountInfo:
        return self.account_result

    def get_symbol_info(self, symbol: str) -> MT5SymbolInfo:
        self.symbol_info_calls.append(symbol)
        return self.symbol_info_result

    def get_tick(self, symbol: str) -> MT5Tick:
        return self.tick_result

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int,
        include_incomplete: bool = False,
    ) -> tuple[MT5Candle, ...]:
        self.candle_calls.append((symbol, timeframe, count, include_incomplete))
        return self.candle_results[timeframe]

    def get_positions(self, symbol: str | None = None) -> tuple[MT5OpenPosition, ...]:
        self.position_calls.append(symbol)
        return self.positions_result


class SequenceClock:
    """Deterministic clock returning the supplied timestamps in order."""

    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)
