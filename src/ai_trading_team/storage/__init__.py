"""Persistence adapters that remain outside trading execution."""

from ai_trading_team.storage.ai_budget import SQLiteBudgetLedger
from ai_trading_team.storage.execution import (
    InMemoryDemoExecutionRepository,
    SQLiteDemoExecutionRepository,
)
from ai_trading_team.storage.observation import (
    InMemoryObservationRepository,
    ObservationRepository,
    SQLiteObservationRepository,
)
from ai_trading_team.storage.qualification import (
    InMemoryQualificationRepository,
    SQLiteQualificationRepository,
)
from ai_trading_team.storage.replay import (
    InMemoryReplayRepository,
    ReplayRepository,
    SQLiteReplayRepository,
)
from ai_trading_team.storage.shadow_audit import (
    DuplicateCycleError,
    InMemoryShadowAuditRepository,
    ShadowAuditRepository,
    SQLiteShadowAuditRepository,
)

__all__ = [
    "DuplicateCycleError",
    "InMemoryShadowAuditRepository",
    "InMemoryReplayRepository",
    "InMemoryObservationRepository",
    "InMemoryQualificationRepository",
    "InMemoryDemoExecutionRepository",
    "ObservationRepository",
    "ReplayRepository",
    "ShadowAuditRepository",
    "SQLiteBudgetLedger",
    "SQLiteShadowAuditRepository",
    "SQLiteReplayRepository",
    "SQLiteObservationRepository",
    "SQLiteQualificationRepository",
    "SQLiteDemoExecutionRepository",
]
