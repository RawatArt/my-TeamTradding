"""Deterministic validation for non-executable trade proposals."""

from dataclasses import dataclass
from decimal import Decimal

from ai_trading_team.config.settings import RiskConstitutionSettings
from ai_trading_team.risk.reasons import risk_reason
from ai_trading_team.schemas.decisions import TradeProposal
from ai_trading_team.schemas.enums import RiskReasonCode, SymbolTradeMode, TradeSide
from ai_trading_team.schemas.market import MarketSnapshot
from ai_trading_team.schemas.risk import RiskReason


@dataclass(frozen=True, slots=True)
class ProposalValidationResult:
    """Validated price distances or ordered rejection reasons."""

    reasons: tuple[RiskReason, ...]
    stop_distance: Decimal | None
    reward_distance: Decimal | None
    risk_reward: Decimal | None

    @property
    def valid(self) -> bool:
        return not self.reasons


class ProposalValidator:
    """Validate geometry and broker capabilities without sizing or execution."""

    def __init__(self, settings: RiskConstitutionSettings) -> None:
        self._settings = settings

    def validate(
        self, proposal: TradeProposal, snapshot: MarketSnapshot
    ) -> ProposalValidationResult:
        reasons: list[RiskReason] = []

        if proposal.cycle_id != snapshot.cycle_id or proposal.snapshot_id != snapshot.snapshot_id:
            reasons.append(
                risk_reason(
                    RiskReasonCode.TRACEABILITY_MISMATCH,
                    "proposal does not belong to the snapshot trace",
                )
            )
        if proposal.symbol != snapshot.symbol:
            reasons.append(
                risk_reason(
                    RiskReasonCode.SYMBOL_MISMATCH,
                    "proposal symbol does not match snapshot symbol",
                )
            )

        entry = proposal.entry
        stop_loss = proposal.stop_loss
        take_profit = proposal.take_profit
        if entry is None:
            reasons.append(risk_reason(RiskReasonCode.ENTRY_PRICE_REQUIRED, "entry is required"))
        elif entry <= 0:
            reasons.append(
                risk_reason(RiskReasonCode.ENTRY_PRICE_INVALID, "entry must be positive")
            )
        if stop_loss is None:
            reasons.append(
                risk_reason(RiskReasonCode.STOP_LOSS_REQUIRED, "stop loss is mandatory")
            )
        elif stop_loss <= 0:
            reasons.append(
                risk_reason(RiskReasonCode.STOP_LOSS_INVALID, "stop loss must be positive")
            )
        if take_profit is None:
            reasons.append(
                risk_reason(
                    RiskReasonCode.TAKE_PROFIT_REQUIRED,
                    "take profit is required to validate minimum risk/reward",
                )
            )
        elif take_profit <= 0:
            reasons.append(
                risk_reason(RiskReasonCode.TAKE_PROFIT_INVALID, "take profit must be positive")
            )

        stop_distance: Decimal | None = None
        reward_distance: Decimal | None = None
        risk_reward: Decimal | None = None
        if (
            entry is not None
            and entry > 0
            and stop_loss is not None
            and stop_loss > 0
            and take_profit is not None
            and take_profit > 0
        ):
            valid_stop = (
                stop_loss < entry
                if proposal.side is TradeSide.BUY
                else stop_loss > entry
            )
            valid_take_profit = (
                take_profit > entry
                if proposal.side is TradeSide.BUY
                else take_profit < entry
            )
            if not valid_stop:
                reasons.append(
                    risk_reason(
                        RiskReasonCode.INVALID_STOP_GEOMETRY,
                        "stop loss is on the wrong side of entry",
                    )
                )
            if not valid_take_profit:
                reasons.append(
                    risk_reason(
                        RiskReasonCode.INVALID_TAKE_PROFIT_GEOMETRY,
                        "take profit is on the wrong side of entry",
                    )
                )
            if valid_stop:
                stop_distance = abs(entry - stop_loss)
            if valid_take_profit:
                reward_distance = abs(take_profit - entry)
            if stop_distance is not None and reward_distance is not None:
                risk_reward = reward_distance / stop_distance
                if risk_reward < self._settings.minimum_risk_reward:
                    reasons.append(
                        risk_reason(
                            RiskReasonCode.RISK_REWARD_BELOW_MINIMUM,
                            "proposal risk/reward is below the configured minimum",
                        )
                    )

        symbol_info = snapshot.symbol_info
        tick_size = symbol_info.trade_tick_size
        point = symbol_info.point
        if tick_size <= 0 or point <= 0:
            reasons.append(
                risk_reason(
                    RiskReasonCode.INVALID_BROKER_RISK_METADATA,
                    "broker tick size and point must be positive",
                )
            )
        else:
            for price in (entry, stop_loss, take_profit):
                if price is not None and price > 0 and price % tick_size != 0:
                    reasons.append(
                        risk_reason(
                            RiskReasonCode.PRICE_NOT_ALIGNED_TO_TICK_SIZE,
                            "proposal price is not aligned to broker tick size",
                        )
                    )
                    break
            minimum_distance = Decimal(symbol_info.trade_stops_level) * point
            if stop_distance is not None and stop_distance < minimum_distance:
                reasons.append(
                    risk_reason(
                        RiskReasonCode.STOP_DISTANCE_BELOW_BROKER_MINIMUM,
                        "stop distance is below the broker minimum",
                    )
                )
            if reward_distance is not None and reward_distance < minimum_distance:
                reasons.append(
                    risk_reason(
                        RiskReasonCode.TAKE_PROFIT_DISTANCE_BELOW_BROKER_MINIMUM,
                        "take-profit distance is below the broker minimum",
                    )
                )

        if symbol_info.trading_mode in (SymbolTradeMode.DISABLED, SymbolTradeMode.CLOSE_ONLY):
            reasons.append(
                risk_reason(
                    RiskReasonCode.SYMBOL_TRADING_DISABLED,
                    "symbol is not enabled for opening trades",
                )
            )
        elif (
            symbol_info.trading_mode is SymbolTradeMode.LONG_ONLY
            and proposal.side is TradeSide.SELL
        ) or (
            symbol_info.trading_mode is SymbolTradeMode.SHORT_ONLY
            and proposal.side is TradeSide.BUY
        ):
            reasons.append(
                risk_reason(
                    RiskReasonCode.TRADE_SIDE_NOT_ALLOWED,
                    "proposal side is not allowed by broker symbol mode",
                )
            )
        if not snapshot.account.trade_allowed:
            reasons.append(
                risk_reason(
                    RiskReasonCode.ACCOUNT_TRADING_DISABLED,
                    "account is not enabled for trading",
                )
            )
        if not snapshot.account.expert_trading_allowed:
            reasons.append(
                risk_reason(
                    RiskReasonCode.EXPERT_TRADING_DISABLED,
                    "account is not enabled for programmatic trading",
                )
            )

        return ProposalValidationResult(
            reasons=tuple(reasons),
            stop_distance=stop_distance,
            reward_distance=reward_distance,
            risk_reward=risk_reward,
        )
