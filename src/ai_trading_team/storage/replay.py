"""Append-only storage-neutral persistence for sanitized M8 replay artifacts."""

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol

from ai_trading_team.replay.errors import DuplicateReplayRecordError
from ai_trading_team.replay.serialization import canonical_replay_bytes, content_digest
from ai_trading_team.schemas.evaluation import PerformanceSummary, TradeOutcome
from ai_trading_team.schemas.replay import FrozenReplayDecision, ReplayConfiguration, ReplayFrame

type ReplayRecord = (
    ReplayConfiguration | ReplayFrame | FrozenReplayDecision | TradeOutcome | PerformanceSummary
)


class ReplayRepository(Protocol):
    """Append-only interface; every read is explicitly partition-scoped."""

    def append_configuration(
        self, replay_id: str, partition_id: str, configuration: ReplayConfiguration
    ) -> None: ...

    def append_frame(self, frame: ReplayFrame) -> None: ...

    def append_decision(self, partition_id: str, decision: FrozenReplayDecision) -> None: ...

    def append_outcome(self, outcome: TradeOutcome) -> None: ...

    def append_summary(self, summary: PerformanceSummary) -> None: ...

    def get(
        self, replay_id: str, partition_id: str, record_id: str
    ) -> tuple[str, bytes] | None: ...


class InMemoryReplayRepository:
    """Thread-safe in-memory implementation used by deterministic tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], tuple[str, bytes]] = {}
        self._identities: set[str] = set()
        self._lock = RLock()

    def append_configuration(
        self, replay_id: str, partition_id: str, configuration: ReplayConfiguration
    ) -> None:
        self._append(replay_id, partition_id, replay_id, "CONFIGURATION", configuration)

    def append_frame(self, frame: ReplayFrame) -> None:
        self._append(frame.replay_id, frame.partition_id, frame.frame_id, "FRAME", frame)

    def append_decision(self, partition_id: str, decision: FrozenReplayDecision) -> None:
        self._append(
            decision.replay_id,
            partition_id,
            decision.frozen_decision_id,
            "DECISION",
            decision,
        )

    def append_outcome(self, outcome: TradeOutcome) -> None:
        self._append(
            outcome.replay_id,
            outcome.partition_id,
            outcome.outcome_id,
            "OUTCOME",
            outcome,
        )

    def append_summary(self, summary: PerformanceSummary) -> None:
        self._append(
            summary.replay_id,
            summary.partition_id,
            summary.summary_id,
            "SUMMARY",
            summary,
        )

    def get(
        self, replay_id: str, partition_id: str, record_id: str
    ) -> tuple[str, bytes] | None:
        with self._lock:
            return self._records.get((replay_id, partition_id, record_id))

    def _append(
        self,
        replay_id: str,
        partition_id: str,
        record_id: str,
        kind: str,
        record: ReplayRecord,
    ) -> None:
        with self._lock:
            if record_id in self._identities:
                raise DuplicateReplayRecordError()
            self._records[(replay_id, partition_id, record_id)] = (
                kind,
                canonical_replay_bytes(record),
            )
            self._identities.add(record_id)


class SQLiteReplayRepository:
    """SQLite adapter that inserts immutable canonical records and never updates them."""

    def __init__(self, path: Path | str) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS replay_records (
                    record_id TEXT PRIMARY KEY,
                    record_kind TEXT NOT NULL,
                    replay_id TEXT NOT NULL,
                    partition_id TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    record_digest TEXT NOT NULL,
                    record_json BLOB NOT NULL
                )
                """
            )
            self._connection.execute(
                """CREATE INDEX IF NOT EXISTS replay_partition_lookup
                ON replay_records(replay_id, partition_id, record_id)"""
            )

    def close(self) -> None:
        self._connection.close()

    def append_configuration(
        self, replay_id: str, partition_id: str, configuration: ReplayConfiguration
    ) -> None:
        self._append(replay_id, partition_id, replay_id, "CONFIGURATION", configuration)

    def append_frame(self, frame: ReplayFrame) -> None:
        self._append(frame.replay_id, frame.partition_id, frame.frame_id, "FRAME", frame)

    def append_decision(self, partition_id: str, decision: FrozenReplayDecision) -> None:
        self._append(
            decision.replay_id,
            partition_id,
            decision.frozen_decision_id,
            "DECISION",
            decision,
        )

    def append_outcome(self, outcome: TradeOutcome) -> None:
        self._append(
            outcome.replay_id,
            outcome.partition_id,
            outcome.outcome_id,
            "OUTCOME",
            outcome,
        )

    def append_summary(self, summary: PerformanceSummary) -> None:
        self._append(
            summary.replay_id,
            summary.partition_id,
            summary.summary_id,
            "SUMMARY",
            summary,
        )

    def get(
        self, replay_id: str, partition_id: str, record_id: str
    ) -> tuple[str, bytes] | None:
        row = self._connection.execute(
            """SELECT record_kind, record_json FROM replay_records
            WHERE replay_id = ? AND partition_id = ? AND record_id = ?""",
            (replay_id, partition_id, record_id),
        ).fetchone()
        return None if row is None else (row["record_kind"], bytes(row["record_json"]))

    def _append(
        self,
        replay_id: str,
        partition_id: str,
        record_id: str,
        kind: str,
        record: ReplayRecord,
    ) -> None:
        payload = canonical_replay_bytes(record)
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """INSERT INTO replay_records
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record_id,
                        kind,
                        replay_id,
                        partition_id,
                        record.schema_version,
                        content_digest(record),
                        payload,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateReplayRecordError() from exc
