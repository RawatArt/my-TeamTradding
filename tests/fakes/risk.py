"""Deterministic M3 boundary fixtures with no terminal dependency."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ai_trading_team.config import MarketDataSettings
from ai_trading_team.market import MarketDataService
from ai_trading_team.risk import account_fingerprint
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import Timeframe, TradeSide
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.mt5 import MT5AccountInfo, MT5OpenPosition, MT5SymbolInfo
from ai_trading_team.schemas.risk import AccountRiskContext
from tests.fakes.market import (
    SNAPSHOT_END,
    SNAPSHOT_START,
    SYMBOL,
    FakeMarketDataSource,
    SequenceClock,
)

CYCLE_ID = "cycle-m3-001"
SNAPSHOT_ID = "snapshot-m3-001"
EVALUATED_AT = SNAPSHOT_END + timedelta(seconds=1)


def risk_snapshot(
    *,
    equity: Decimal = Decimal("50.00"),
    symbol_info: MT5SymbolInfo | None = None,
    positions: tuple[MT5OpenPosition, ...] = (),
    trade_allowed: bool = True,
    expert_trading_allowed: bool = True,
) -> MarketSnapshot:
    source = FakeMarketDataSource()
    account_payload = source.account_result.model_dump(mode="python")
    account_payload.update(
        equity=equity,
        trade_allowed=trade_allowed,
        expert_trading_allowed=expert_trading_allowed,
    )
    source.account_result = MT5AccountInfo.model_validate(account_payload)
    if symbol_info is not None:
        source.symbol_info_result = symbol_info
    source.positions_result = positions
    return MarketDataService(
        source,
        MarketDataSettings(m15_candle_count=2, h1_candle_count=2, h4_candle_count=2),
        SYMBOL,
        clock=SequenceClock(
            SNAPSHOT_START,
            SNAPSHOT_START + timedelta(seconds=3),
            SNAPSHOT_END,
        ),
    ).build_snapshot(CYCLE_ID, SNAPSHOT_ID, Timeframe.M15)


def proposal(
    *,
    side: TradeSide = TradeSide.BUY,
    entry: Decimal | None = Decimal("1.08130"),
    stop_loss: Decimal | None = Decimal("1.08110"),
    take_profit: Decimal | None = Decimal("1.08160"),
    cycle_id: str = CYCLE_ID,
    snapshot_id: str = SNAPSHOT_ID,
    symbol: str = SYMBOL,
) -> TradeProposal:
    return TradeProposal(
        cycle_id=cycle_id,
        snapshot_id=snapshot_id,
        timestamp=SNAPSHOT_END,
        proposal_id="proposal-m3-001",
        symbol=symbol,
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        rationale="Deterministic test proposal",
    )


def account_context(
    snapshot: MarketSnapshot,
    *,
    account_ref: str | None = None,
    context_as_of: datetime = SNAPSHOT_END,
    peak_equity: Decimal = Decimal("50.00"),
    day_start_equity: Decimal = Decimal("50.00"),
    open_position_count: int = 0,
    cycle_id: str = CYCLE_ID,
    snapshot_id: str = SNAPSHOT_ID,
) -> AccountRiskContext:
    return AccountRiskContext(
        cycle_id=cycle_id,
        snapshot_id=snapshot_id,
        account_ref=account_ref
        or account_fingerprint(snapshot.account.account_id, snapshot.account.server),
        context_as_of=context_as_of,
        trading_day_started_at=datetime(2026, 9, 10, tzinfo=UTC),
        cash_flow_adjusted_peak_equity=peak_equity,
        adjusted_day_start_equity=day_start_equity,
        account_open_position_count=open_position_count,
    )
