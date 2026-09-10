from decimal import Decimal

import pytest
from tests.fakes.market import symbol_info
from tests.fakes.risk import proposal, risk_snapshot

from ai_trading_team.config import RiskConstitutionSettings
from ai_trading_team.risk import ProposalValidator
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import RiskReasonCode, SymbolTradeMode, TradeSide
from ai_trading_team.schemas.mt5 import MT5SymbolInfo


def reason_codes(**changes: object) -> tuple[RiskReasonCode, ...]:
    payload = proposal().model_dump(mode="python")
    payload.update(changes)
    result = ProposalValidator(RiskConstitutionSettings()).validate(
        TradeProposal.model_validate(payload), risk_snapshot()
    )
    return tuple(reason.code for reason in result.reasons)


def changed_symbol_info(**changes: object) -> MT5SymbolInfo:
    payload = symbol_info().model_dump(mode="python")
    payload.update(changes)
    return MT5SymbolInfo.model_validate(payload)


def test_valid_buy_geometry_and_risk_reward_are_accepted() -> None:
    result = ProposalValidator(RiskConstitutionSettings()).validate(
        proposal(), risk_snapshot()
    )

    assert result.valid
    assert result.stop_distance == Decimal("0.00020")
    assert result.reward_distance == Decimal("0.00030")
    assert result.risk_reward == Decimal("1.5")


def test_valid_sell_geometry_is_accepted() -> None:
    result = ProposalValidator(RiskConstitutionSettings()).validate(
        proposal(
            side=TradeSide.SELL,
            stop_loss=Decimal("1.08150"),
            take_profit=Decimal("1.08100"),
        ),
        risk_snapshot(),
    )

    assert result.valid
    assert result.stop_distance == Decimal("0.00020")
    assert result.reward_distance == Decimal("0.00030")


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"stop_loss": None}, RiskReasonCode.STOP_LOSS_REQUIRED),
        ({"stop_loss": Decimal("1.08130")}, RiskReasonCode.INVALID_STOP_GEOMETRY),
        ({"stop_loss": Decimal("1.08140")}, RiskReasonCode.INVALID_STOP_GEOMETRY),
        ({"take_profit": Decimal("1.08120")}, RiskReasonCode.INVALID_TAKE_PROFIT_GEOMETRY),
        ({"entry": Decimal("0")}, RiskReasonCode.ENTRY_PRICE_INVALID),
        ({"entry": Decimal("-1")}, RiskReasonCode.ENTRY_PRICE_INVALID),
        ({"stop_loss": Decimal("0")}, RiskReasonCode.STOP_LOSS_INVALID),
        ({"take_profit": Decimal("0")}, RiskReasonCode.TAKE_PROFIT_INVALID),
        (
            {"take_profit": Decimal("1.08150")},
            RiskReasonCode.RISK_REWARD_BELOW_MINIMUM,
        ),
    ],
)
def test_invalid_price_contracts_produce_typed_reasons(
    changes: dict[str, object], expected: RiskReasonCode
) -> None:
    assert expected in reason_codes(**changes)


def test_price_must_align_to_broker_tick_size() -> None:
    assert RiskReasonCode.PRICE_NOT_ALIGNED_TO_TICK_SIZE in reason_codes(
        entry=Decimal("1.081305")
    )


def test_stop_distance_honors_broker_stops_level() -> None:
    assert RiskReasonCode.STOP_DISTANCE_BELOW_BROKER_MINIMUM in reason_codes(
        stop_loss=Decimal("1.08115")
    )


@pytest.mark.parametrize(
    ("mode", "side", "expected"),
    [
        (SymbolTradeMode.DISABLED, TradeSide.BUY, RiskReasonCode.SYMBOL_TRADING_DISABLED),
        (SymbolTradeMode.CLOSE_ONLY, TradeSide.SELL, RiskReasonCode.SYMBOL_TRADING_DISABLED),
        (SymbolTradeMode.LONG_ONLY, TradeSide.SELL, RiskReasonCode.TRADE_SIDE_NOT_ALLOWED),
        (SymbolTradeMode.SHORT_ONLY, TradeSide.BUY, RiskReasonCode.TRADE_SIDE_NOT_ALLOWED),
    ],
)
def test_broker_trading_capability_is_enforced(
    mode: SymbolTradeMode, side: TradeSide, expected: RiskReasonCode
) -> None:
    snapshot = risk_snapshot(symbol_info=changed_symbol_info(trading_mode=mode))
    candidate = (
        proposal(side=side)
        if side is TradeSide.BUY
        else proposal(
            side=side,
            stop_loss=Decimal("1.08150"),
            take_profit=Decimal("1.08100"),
        )
    )

    result = ProposalValidator(RiskConstitutionSettings()).validate(candidate, snapshot)

    assert expected in tuple(reason.code for reason in result.reasons)


def test_account_trading_capabilities_are_enforced() -> None:
    result = ProposalValidator(RiskConstitutionSettings()).validate(
        proposal(), risk_snapshot(trade_allowed=False, expert_trading_allowed=False)
    )

    assert tuple(reason.code for reason in result.reasons)[-2:] == (
        RiskReasonCode.ACCOUNT_TRADING_DISABLED,
        RiskReasonCode.EXPERT_TRADING_DISABLED,
    )
