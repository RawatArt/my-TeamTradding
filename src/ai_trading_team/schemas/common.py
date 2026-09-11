"""Shared validation primitives for stable boundary contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CycleId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
SnapshotId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
AccountReference = Annotated[
    str,
    StringConstraints(pattern=r"^acct-v1:[0-9a-f]{64}$"),
]
SchemaVersion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d+\.\d+\.\d+$"),
]
Symbol = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
AgentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ContentDigest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]

FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"), allow_inf_nan=False)]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"), allow_inf_nan=False)]
Percentage = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("100"), allow_inf_nan=False),
]
PerTradeRiskPercentage = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("1"), allow_inf_nan=False),
]
Confidence = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("1"), allow_inf_nan=False),
]


class CoreModel(BaseModel):
    """Strict, immutable base for data crossing component boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class VersionedObservation(CoreModel):
    """Version and capture time for external observations outside a decision cycle."""

    schema_version: SchemaVersion = "1.0.0"
    retrieved_at: datetime

    @field_validator("retrieved_at")
    @classmethod
    def require_retrieved_timezone_and_normalize_utc(cls, value: datetime) -> datetime:
        """Reject naive retrieval times and normalize aware values to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value.astimezone(UTC)


class TraceableRecord(CoreModel):
    """Required trace envelope for every decision-cycle-bound record."""

    cycle_id: CycleId
    schema_version: SchemaVersion = "1.0.0"
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def require_timezone_and_normalize_utc(cls, value: datetime) -> datetime:
        """Reject naive datetimes and normalize aware values to UTC."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
