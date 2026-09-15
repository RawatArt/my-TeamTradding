"""Atomic, single-use M11 real-DEMO readiness persistence."""

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from ai_trading_team.replay.serialization import content_digest
from ai_trading_team.schemas.enums import ExecutionControlState
from ai_trading_team.schemas.execution import ExecutionControlEvent
from ai_trading_team.schemas.execution_acceptance import (
    RealDemoAcceptanceRecord,
    RealDemoMutationApproval,
    RealDemoReadinessRecord,
)


class InMemoryRealDemoAcceptanceRepository:
    """Atomic readiness registration/consumption; no dispatch behavior."""

    def __init__(self) -> None:
        self._readiness: dict[str, RealDemoReadinessRecord] = {}
        self._consumed: dict[str, str] = {}
        self._results: dict[str, RealDemoAcceptanceRecord] = {}
        self._lock = RLock()

    def add_readiness(self, readiness: RealDemoReadinessRecord) -> None:
        with self._lock:
            if readiness.acceptance_run_id in self._readiness or any(
                item.readiness_generation_id == readiness.readiness_generation_id
                for item in self._readiness.values()
            ):
                raise ValueError("readiness run or generation already exists")
            self._readiness[readiness.acceptance_run_id] = readiness

    def consume(
        self,
        readiness: RealDemoReadinessRecord,
        approval: RealDemoMutationApproval,
        control_event: ExecutionControlEvent,
        *,
        consumed_at: datetime,
    ) -> None:
        with self._lock:
            stored = self._readiness.get(readiness.acceptance_run_id)
            if stored != readiness or readiness.readiness_digest != content_digest(
                readiness.model_dump(mode="python", exclude={"readiness_digest"})
            ):
                raise ValueError("readiness evidence is absent or has changed")
            if readiness.readiness_generation_id in self._consumed:
                raise ValueError("readiness evidence was already consumed")
            if consumed_at >= readiness.readiness_expires_at or not approval.applies_at(
                consumed_at
            ):
                raise ValueError("readiness or mutation approval has expired")
            checks = (
                approval.acceptance_run_id == readiness.acceptance_run_id,
                approval.readiness_generation_id == readiness.readiness_generation_id,
                approval.readiness_digest == readiness.readiness_digest,
                approval.readiness_created_at == readiness.readiness_created_at,
                approval.readiness_expires_at == readiness.readiness_expires_at,
                approval.candidate_id == readiness.candidate_id,
                approval.candidate_digest == readiness.candidate_digest,
                approval.candidate_generation_id == readiness.candidate_generation_id,
                approval.candidate_generation_digest == readiness.candidate_generation_digest,
                approval.account_ref == readiness.account_ref,
                approval.environment_ref == readiness.environment_ref,
                approval.environment_acceptance_id == readiness.environment_acceptance_id,
                approval.environment_acceptance_digest
                == readiness.environment_acceptance_digest,
                approval.policy_ref == readiness.policy_ref,
                approval.policy_version == readiness.policy_version,
                approval.policy_digest == readiness.policy_digest,
                approval.execution_control_event_id == readiness.execution_control_event_id,
                approval.execution_control_event_digest
                == readiness.execution_control_event_digest,
                approval.execution_control_event_id == control_event.event_id,
                approval.execution_control_event_digest == content_digest(control_event),
                approval.execution_control_state is ExecutionControlState.ENABLED,
                control_event.state is ExecutionControlState.ENABLED,
                approval.submission_limit == 1,
            )
            if not all(checks):
                raise ValueError("mutation approval does not bind this exact readiness generation")
            self._consumed[readiness.readiness_generation_id] = approval.mutation_approval_id

    def is_consumed(self, readiness_generation_id: str) -> bool:
        return readiness_generation_id in self._consumed

    def save_result(self, record: RealDemoAcceptanceRecord) -> None:
        with self._lock:
            if record.acceptance_run_id in self._results:
                raise ValueError("acceptance result already exists")
            if record.readiness_generation_id not in self._consumed:
                raise ValueError("acceptance result requires consumed readiness")
            self._results[record.acceptance_run_id] = record


class SQLiteRealDemoAcceptanceRepository(InMemoryRealDemoAcceptanceRepository):
    """Durable readiness consumption prevents reuse after process restart."""

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_real_demo_readiness (
                acceptance_run_id TEXT PRIMARY KEY,
                readiness_generation_id TEXT NOT NULL UNIQUE,
                record_json TEXT NOT NULL)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_real_demo_consumption (
                readiness_generation_id TEXT PRIMARY KEY,
                mutation_approval_id TEXT NOT NULL UNIQUE)"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS m11_real_demo_result (
                acceptance_run_id TEXT PRIMARY KEY,
                record_json TEXT NOT NULL)"""
            )
        self._load()

    def close(self) -> None:
        self._connection.close()

    def add_readiness(self, readiness: RealDemoReadinessRecord) -> None:
        super().add_readiness(readiness)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_real_demo_readiness VALUES (?, ?, ?)",
                    (
                        readiness.acceptance_run_id,
                        readiness.readiness_generation_id,
                        readiness.model_dump_json(),
                    ),
                )
        except Exception:
            self._readiness.pop(readiness.acceptance_run_id, None)
            raise

    def consume(
        self,
        readiness: RealDemoReadinessRecord,
        approval: RealDemoMutationApproval,
        control_event: ExecutionControlEvent,
        *,
        consumed_at: datetime,
    ) -> None:
        super().consume(readiness, approval, control_event, consumed_at=consumed_at)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_real_demo_consumption VALUES (?, ?)",
                    (readiness.readiness_generation_id, approval.mutation_approval_id),
                )
        except Exception:
            self._consumed.pop(readiness.readiness_generation_id, None)
            raise

    def save_result(self, record: RealDemoAcceptanceRecord) -> None:
        super().save_result(record)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO m11_real_demo_result VALUES (?, ?)",
                    (record.acceptance_run_id, record.model_dump_json()),
                )
        except Exception:
            self._results.pop(record.acceptance_run_id, None)
            raise

    def _load(self) -> None:
        for row in self._connection.execute(
            "SELECT record_json FROM m11_real_demo_readiness"
        ):
            readiness_item = RealDemoReadinessRecord.model_validate_json(row[0])
            self._readiness[readiness_item.acceptance_run_id] = readiness_item
        for row in self._connection.execute(
            "SELECT readiness_generation_id, mutation_approval_id "
            "FROM m11_real_demo_consumption"
        ):
            self._consumed[str(row[0])] = str(row[1])
        for row in self._connection.execute("SELECT record_json FROM m11_real_demo_result"):
            result_item = RealDemoAcceptanceRecord.model_validate_json(row[0])
            self._results[result_item.acceptance_run_id] = result_item
