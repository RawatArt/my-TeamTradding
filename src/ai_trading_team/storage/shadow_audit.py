"""Append-only SQLite persistence for M6 shadow decision cycles."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Protocol

from ai_trading_team.schemas.enums import CycleClaimState
from ai_trading_team.schemas.shadow import CycleClaim, ShadowDecisionRecord


class DuplicateCycleError(RuntimeError):
    """Raised when a claimed cycle identity is presented again."""


class ShadowAuditRepository(Protocol):
    """Storage-neutral cycle claim and final audit contract."""

    def claim_cycle(
        self, cycle_id: str, snapshot_id: str, *, at: datetime
    ) -> CycleClaim: ...

    def finalize(self, record: ShadowDecisionRecord) -> None: ...

    def abandon(self, cycle_id: str, *, at: datetime, reason: str) -> CycleClaim: ...

    def get_claim(self, cycle_id: str) -> CycleClaim | None: ...

    def get_record(self, cycle_id: str) -> ShadowDecisionRecord | None: ...


class InMemoryShadowAuditRepository:
    """Thread-safe test repository with the same no-replay semantics as SQLite."""

    def __init__(self) -> None:
        self._claims: dict[str, CycleClaim] = {}
        self._records: dict[str, ShadowDecisionRecord] = {}
        self._lock = RLock()

    def claim_cycle(self, cycle_id: str, snapshot_id: str, *, at: datetime) -> CycleClaim:
        with self._lock:
            if cycle_id in self._claims:
                raise DuplicateCycleError("cycle identity has already been claimed")
            moment = _utc(at)
            claim = CycleClaim(
                cycle_id=cycle_id,
                snapshot_id=snapshot_id,
                state=CycleClaimState.INCOMPLETE,
                claimed_at=moment,
                updated_at=moment,
            )
            self._claims[cycle_id] = claim
            return claim

    def finalize(self, record: ShadowDecisionRecord) -> None:
        with self._lock:
            cycle_id = record.decision_cycle.cycle_id
            claim = self._require_incomplete(cycle_id)
            if claim.snapshot_id != record.decision_cycle.initial_snapshot_id:
                raise ValueError("final record snapshot does not match cycle claim")
            self._records[cycle_id] = record
            self._claims[cycle_id] = claim.model_copy(
                update={
                    "state": CycleClaimState.FINALIZED,
                    "updated_at": record.recorded_at,
                }
            )

    def abandon(self, cycle_id: str, *, at: datetime, reason: str) -> CycleClaim:
        with self._lock:
            claim = self._require_incomplete(cycle_id)
            updated = claim.model_copy(
                update={
                    "state": CycleClaimState.ABANDONED,
                    "updated_at": _utc(at),
                    "sanitized_reason": reason,
                }
            )
            updated = CycleClaim.model_validate(updated.model_dump())
            self._claims[cycle_id] = updated
            return updated

    def get_claim(self, cycle_id: str) -> CycleClaim | None:
        with self._lock:
            return self._claims.get(cycle_id)

    def get_record(self, cycle_id: str) -> ShadowDecisionRecord | None:
        with self._lock:
            return self._records.get(cycle_id)

    def _require_incomplete(self, cycle_id: str) -> CycleClaim:
        claim = self._claims.get(cycle_id)
        if claim is None:
            raise KeyError("cycle claim does not exist")
        if claim.state is not CycleClaimState.INCOMPLETE:
            raise ValueError("only an incomplete cycle may transition")
        return claim


class SQLiteShadowAuditRepository:
    """SQLite implementation with atomic claims and immutable finalized records."""

    def __init__(self, path: Path | str) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_cycle_claims (
                    cycle_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sanitized_reason TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_decision_records (
                    cycle_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL UNIQUE,
                    schema_version TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(cycle_id) REFERENCES shadow_cycle_claims(cycle_id)
                )
                """
            )

    def close(self) -> None:
        self._connection.close()

    def claim_cycle(self, cycle_id: str, snapshot_id: str, *, at: datetime) -> CycleClaim:
        moment = _utc(at)
        claim = CycleClaim(
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            state=CycleClaimState.INCOMPLETE,
            claimed_at=moment,
            updated_at=moment,
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT INTO shadow_cycle_claims
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        cycle_id,
                        snapshot_id,
                        claim.state.value,
                        moment.isoformat(),
                        moment.isoformat(),
                        None,
                    ),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as exc:
                self._connection.rollback()
                raise DuplicateCycleError("cycle identity has already been claimed") from exc
            except Exception:
                self._connection.rollback()
                raise
        return claim

    def finalize(self, record: ShadowDecisionRecord) -> None:
        cycle_id = record.decision_cycle.cycle_id
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                claim = self._require_incomplete(cycle_id)
                if claim.snapshot_id != record.decision_cycle.initial_snapshot_id:
                    raise ValueError("final record snapshot does not match cycle claim")
                self._connection.execute(
                    """INSERT INTO shadow_decision_records
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        cycle_id,
                        record.record_id,
                        record.schema_version,
                        record.model_dump_json(),
                        record.recorded_at.isoformat(),
                    ),
                )
                self._connection.execute(
                    """UPDATE shadow_cycle_claims
                    SET state = ?, updated_at = ? WHERE cycle_id = ?""",
                    (
                        CycleClaimState.FINALIZED.value,
                        record.recorded_at.isoformat(),
                        cycle_id,
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def abandon(self, cycle_id: str, *, at: datetime, reason: str) -> CycleClaim:
        moment = _utc(at)
        with self._lock, self._connection:
            self._require_incomplete(cycle_id)
            self._connection.execute(
                """UPDATE shadow_cycle_claims
                SET state = ?, updated_at = ?, sanitized_reason = ? WHERE cycle_id = ?""",
                (CycleClaimState.ABANDONED.value, moment.isoformat(), reason, cycle_id),
            )
        claim = self.get_claim(cycle_id)
        assert claim is not None
        return claim

    def get_claim(self, cycle_id: str) -> CycleClaim | None:
        row = self._connection.execute(
            "SELECT * FROM shadow_cycle_claims WHERE cycle_id = ?", (cycle_id,)
        ).fetchone()
        if row is None:
            return None
        return CycleClaim(
            cycle_id=row["cycle_id"],
            snapshot_id=row["snapshot_id"],
            state=row["state"],
            claimed_at=datetime.fromisoformat(row["claimed_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            sanitized_reason=row["sanitized_reason"],
        )

    def get_record(self, cycle_id: str) -> ShadowDecisionRecord | None:
        row = self._connection.execute(
            "SELECT record_json FROM shadow_decision_records WHERE cycle_id = ?", (cycle_id,)
        ).fetchone()
        return None if row is None else ShadowDecisionRecord.model_validate_json(row[0])

    def _require_incomplete(self, cycle_id: str) -> CycleClaim:
        claim = self.get_claim(cycle_id)
        if claim is None:
            raise KeyError("cycle claim does not exist")
        if claim.state is not CycleClaimState.INCOMPLETE:
            raise ValueError("only an incomplete cycle may transition")
        return claim


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
