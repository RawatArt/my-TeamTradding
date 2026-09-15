"""Audited Decimal-to-float conversion at the final MT5 request boundary."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.execution import DemoOrderIntent
from ai_trading_team.schemas.execution_acceptance import (
    VendorBoundaryAudit,
    VendorFloatValueAudit,
)
from ai_trading_team.schemas.mt5 import MT5SymbolInfo


def build_vendor_boundary_audit(
    intent: DemoOrderIntent,
    symbol_info: MT5SymbolInfo,
    *,
    audited_at: datetime,
) -> VendorBoundaryAudit:
    """Fail before dispatch unless every value survives reviewed grid normalization."""
    values = {
        "reference_price": _value_audit(
            "reference_price", intent.reference_price, symbol_info.trade_tick_size
        ),
        "volume": _volume_audit(intent.volume, symbol_info),
        "stop_loss": _value_audit("stop_loss", intent.stop_loss, symbol_info.trade_tick_size),
        "take_profit": _value_audit(
            "take_profit", intent.take_profit, symbol_info.trade_tick_size
        ),
    }
    payload: dict[str, Any] = {
        "execution_intent_id": intent.execution_intent_id,
        "intent_digest": intent.intent_digest,
        "audited_at": audited_at,
        **values,
    }
    normalized = VendorBoundaryAudit.model_validate(
        {**payload, "audit_digest": "sha256:" + "0" * 64}
    )
    return normalized.model_copy(
        update={
            "audit_digest": content_digest(
                normalized.model_dump(mode="python", exclude={"audit_digest"})
            )
        }
    )


def verify_vendor_boundary_audit(audit: VendorBoundaryAudit) -> bool:
    return audit.audit_digest == content_digest(
        audit.model_dump(mode="python", exclude={"audit_digest"})
    )


def _value_audit(
    field_name: Literal["reference_price", "stop_loss", "take_profit"],
    source: Decimal,
    increment: Decimal,
) -> VendorFloatValueAudit:
    return _audit(field_name, source, increment, Decimal("0"))


def _volume_audit(source: Decimal, symbol_info: MT5SymbolInfo) -> VendorFloatValueAudit:
    if not symbol_info.volume_min <= source <= symbol_info.volume_max:
        raise ValueError("volume is outside broker bounds")
    if (source - symbol_info.volume_min) % symbol_info.volume_step != 0:
        raise ValueError("volume is not aligned to the broker volume grid")
    return _audit("volume", source, symbol_info.volume_step, symbol_info.volume_min)


def _audit(
    field_name: Literal["reference_price", "volume", "stop_loss", "take_profit"],
    source: Decimal,
    increment: Decimal,
    anchor: Decimal,
) -> VendorFloatValueAudit:
    if increment <= 0 or (source - anchor) % increment != 0:
        raise ValueError(f"{field_name} is not aligned to the broker grid")
    transported = float(source)
    exact_binary = Decimal.from_float(transported)
    display_value = Decimal(str(transported))
    tolerance = increment / Decimal("2")
    difference = exact_binary - source
    if display_value != source or abs(difference) > tolerance:
        raise ValueError(f"{field_name} float normalization exceeds policy tolerance")
    return VendorFloatValueAudit(
        field_name=field_name,
        source_decimal=source,
        float_repr=repr(transported),
        float_hex=transported.hex(),
        decimal_from_float=exact_binary,
        decimal_from_string=display_value,
        broker_normalized_decimal=display_value,
        conversion_difference=difference,
        broker_increment=increment,
        policy_tolerance=tolerance,
        broker_grid_aligned=True,
        within_policy_tolerance=True,
    )
