"""Normalize M11-specific vendor capabilities and submission results."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast

from ai_trading_team.execution.identifiers import symbol_definition_digest
from ai_trading_team.schemas.enums import (
    DemoFillingMode,
    DemoOrderExecutionMode,
    DemoSubmissionDisposition,
)
from ai_trading_team.schemas.execution import (
    CompositeBrokerEvidence,
    DemoOrderCheckResult,
    DemoOrderIntent,
    DemoSubmissionReceipt,
    DemoSymbolExecutionCapabilities,
)
from ai_trading_team.schemas.mt5 import MT5SymbolInfo


class ConstantSource(Protocol):
    def constant(self, name: str) -> int: ...


def vendor_mapping(raw: object) -> Mapping[str, object]:
    if isinstance(raw, Mapping):
        return cast(Mapping[str, object], raw)
    asdict = getattr(raw, "_asdict", None)
    if callable(asdict):
        value = asdict()
        if isinstance(value, Mapping):
            return cast(Mapping[str, object], value)
    raise ValueError("vendor result has an unsupported shape")


def map_execution_capabilities(
    raw: object,
    symbol_info: MT5SymbolInfo,
    constants: ConstantSource,
    observed_at: datetime,
) -> DemoSymbolExecutionCapabilities:
    data = vendor_mapping(raw)
    execution_mode = DemoOrderExecutionMode(_integer(data, "trade_exemode"))
    fill_flags = _integer(data, "filling_mode")
    order_flags = _integer(data, "order_mode")
    filling: set[DemoFillingMode] = set()
    if fill_flags & constants.constant("SYMBOL_FILLING_FOK"):
        filling.add(DemoFillingMode.FOK)
    if fill_flags & constants.constant("SYMBOL_FILLING_IOC"):
        filling.add(DemoFillingMode.IOC)
    if execution_mode is not DemoOrderExecutionMode.MARKET:
        filling.add(DemoFillingMode.RETURN)
    return DemoSymbolExecutionCapabilities(
        symbol=symbol_info.symbol,
        observed_at=observed_at,
        symbol_info_digest=symbol_definition_digest(symbol_info),
        execution_mode=execution_mode,
        filling_modes=frozenset(filling),
        market_order_allowed=bool(order_flags & constants.constant("SYMBOL_ORDER_MARKET")),
        stop_loss_allowed=bool(order_flags & constants.constant("SYMBOL_ORDER_SL")),
        take_profit_allowed=bool(order_flags & constants.constant("SYMBOL_ORDER_TP")),
    )


def map_order_check(
    raw: object,
    intent: DemoOrderIntent,
    checked_at: datetime,
) -> DemoOrderCheckResult:
    data = vendor_mapping(raw)
    code = _integer(data, "retcode")
    return DemoOrderCheckResult(
        execution_intent_id=intent.execution_intent_id,
        intent_digest=intent.intent_digest,
        checked_at=checked_at,
        accepted=code == 0,
        broker_code=code,
        sanitized_detail="broker check accepted" if code == 0 else "broker check rejected",
    )


def map_submission_receipt(
    raw: object | None,
    intent: DemoOrderIntent,
    constants: ConstantSource,
    *,
    dispatch_started_at: datetime,
    dispatch_completed_at: datetime,
    account_ref: str,
    environment_ref: str,
) -> DemoSubmissionReceipt:
    if raw is None:
        return DemoSubmissionReceipt(
            execution_intent_id=intent.execution_intent_id,
            intent_digest=intent.intent_digest,
            disposition=DemoSubmissionDisposition.UNKNOWN,
            dispatch_started_at=dispatch_started_at,
            dispatch_completed_at=dispatch_completed_at,
            sanitized_detail="broker returned no submission result",
        )
    data = vendor_mapping(raw)
    code = _integer(data, "retcode")
    accepted_codes = {
        constants.constant("TRADE_RETCODE_DONE"),
        constants.constant("TRADE_RETCODE_PLACED"),
        constants.constant("TRADE_RETCODE_DONE_PARTIAL"),
    }
    disposition = (
        DemoSubmissionDisposition.ACCEPTED
        if code in accepted_codes
        else DemoSubmissionDisposition.REJECTED
    )
    evidence = None
    if disposition is DemoSubmissionDisposition.ACCEPTED:
        evidence = CompositeBrokerEvidence(
            account_ref=account_ref,
            environment_ref=environment_ref,
            symbol=intent.symbol,
            side=intent.side,
            volume=_decimal(data, "volume"),
            dispatch_started_at=dispatch_started_at,
            dispatch_completed_at=dispatch_completed_at,
            observed_at=dispatch_completed_at,
            client_trade_reference=intent.client_trade_id,
            broker_order_id=_positive_or_none(data.get("order")),
            broker_deal_id=_positive_or_none(data.get("deal")),
            fill_price=_positive_decimal_or_none(data.get("price")),
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            magic=intent.magic,
            comment=None,
        )
    return DemoSubmissionReceipt(
        execution_intent_id=intent.execution_intent_id,
        intent_digest=intent.intent_digest,
        disposition=disposition,
        dispatch_started_at=dispatch_started_at,
        dispatch_completed_at=dispatch_completed_at,
        broker_code=code,
        evidence=evidence,
        sanitized_detail=(
            "broker accepted protected DEMO request"
            if disposition is DemoSubmissionDisposition.ACCEPTED
            else "broker rejected protected DEMO request"
        ),
    )


def _integer(data: Mapping[str, object], name: str) -> int:
    value = data.get(name)
    if isinstance(value, bool):
        raise ValueError("vendor integer field is invalid")
    try:
        return int(cast(int | str, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("vendor integer field is invalid") from exc


def _decimal(data: Mapping[str, object], name: str) -> Decimal:
    value = data.get(name)
    if isinstance(value, bool):
        raise ValueError("vendor decimal field is invalid")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("vendor decimal field must be finite")
    return result


def _positive_or_none(value: object) -> int | None:
    parsed = int(cast(int | str, value))
    return parsed if parsed > 0 else None


def _positive_decimal_or_none(value: object) -> Decimal | None:
    parsed = Decimal(str(value))
    return parsed if parsed > 0 else None
