"""SQLite-backed atomic M5 AI-budget reservation ledger."""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock

from ai_trading_team.runtime.errors import RuntimeInvocationError
from ai_trading_team.schemas.enums import BudgetReservationState, RuntimeFailureCategory
from ai_trading_team.schemas.runtime import AIBudgetPolicy, BudgetReservation


class SQLiteBudgetLedger:
    """Persist reservations and enforce duplicate/call/cost limits in one transaction."""

    def __init__(self, path: Path | str) -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_budget_reservations (
                    invocation_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    policy_ref TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reserved_amount TEXT NOT NULL,
                    settled_amount TEXT,
                    currency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        self._connection.close()

    def get(self, invocation_id: str) -> BudgetReservation | None:
        row = self._connection.execute(
            "SELECT * FROM ai_budget_reservations WHERE invocation_id = ?",
            (invocation_id,),
        ).fetchone()
        return None if row is None else self._to_model(row)

    def reserve_if_within(
        self,
        reservation: BudgetReservation,
        policy: AIBudgetPolicy,
    ) -> BudgetReservation:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = self._connection.execute(
                    "SELECT 1 FROM ai_budget_reservations WHERE invocation_id = ?",
                    (reservation.invocation_id,),
                ).fetchone()
                if duplicate is not None:
                    raise RuntimeInvocationError(
                        RuntimeFailureCategory.DUPLICATE_INVOCATION,
                        "invocation identity has already been reserved",
                    )
                rows = self._connection.execute(
                    """
                    SELECT * FROM ai_budget_reservations
                    WHERE policy_ref = ? AND state != ?
                    """,
                    (policy.policy_ref, BudgetReservationState.RELEASED.value),
                ).fetchall()
                active = tuple(self._to_model(row) for row in rows)
                same_cycle = sum(item.cycle_id == reservation.cycle_id for item in active)
                same_day = tuple(
                    item
                    for item in active
                    if item.created_at.date() == reservation.created_at.date()
                )
                same_month = tuple(
                    item
                    for item in active
                    if (item.created_at.year, item.created_at.month)
                    == (reservation.created_at.year, reservation.created_at.month)
                )
                if same_cycle >= policy.maximum_calls_per_cycle:
                    raise self._budget_error("maximum calls per cycle exceeded")
                if len(same_day) >= policy.maximum_calls_per_day:
                    raise self._budget_error("maximum calls per day exceeded")
                if self._total(same_day) + reservation.reserved_amount > policy.daily_budget:
                    raise self._budget_error("daily AI budget exceeded")
                if self._total(same_month) + reservation.reserved_amount > policy.monthly_budget:
                    raise self._budget_error("monthly AI budget exceeded")
                self._connection.execute(
                    """
                    INSERT INTO ai_budget_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reservation.invocation_id,
                        reservation.cycle_id,
                        reservation.policy_ref,
                        reservation.state.value,
                        str(reservation.reserved_amount),
                        None,
                        reservation.currency,
                        reservation.created_at.isoformat(),
                        reservation.updated_at.isoformat(),
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return reservation

    def mark_dispatched(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            BudgetReservationState.RESERVED,
            BudgetReservationState.DISPATCHED,
            at,
        )

    def settle(
        self, invocation_id: str, amount: Decimal, *, at: datetime
    ) -> BudgetReservation:
        with self._lock, self._connection:
            current = self._require(invocation_id)
            if current.state is not BudgetReservationState.DISPATCHED:
                raise ValueError("only dispatched reservations may be settled")
            if amount < 0 or amount > current.reserved_amount:
                raise ValueError("settled amount must be within the reserved amount")
            self._connection.execute(
                """
                UPDATE ai_budget_reservations
                SET state = ?, settled_amount = ?, updated_at = ?
                WHERE invocation_id = ?
                """,
                (
                    BudgetReservationState.SETTLED.value,
                    str(amount),
                    at.astimezone(UTC).isoformat(),
                    invocation_id,
                ),
            )
            return self._require(invocation_id)

    def release(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            BudgetReservationState.RESERVED,
            BudgetReservationState.RELEASED,
            at,
        )

    def mark_uncertain(self, invocation_id: str, *, at: datetime) -> BudgetReservation:
        return self._transition(
            invocation_id,
            BudgetReservationState.DISPATCHED,
            BudgetReservationState.UNCERTAIN,
            at,
        )

    def _transition(
        self,
        invocation_id: str,
        expected: BudgetReservationState,
        target: BudgetReservationState,
        at: datetime,
    ) -> BudgetReservation:
        with self._lock, self._connection:
            current = self._require(invocation_id)
            if current.state is not expected:
                raise ValueError(f"reservation must be {expected.value} before {target.value}")
            self._connection.execute(
                """
                UPDATE ai_budget_reservations SET state = ?, updated_at = ?
                WHERE invocation_id = ?
                """,
                (target.value, at.astimezone(UTC).isoformat(), invocation_id),
            )
            return self._require(invocation_id)

    def _require(self, invocation_id: str) -> BudgetReservation:
        item = self.get(invocation_id)
        if item is None:
            raise KeyError("budget reservation does not exist")
        return item

    @staticmethod
    def _to_model(row: sqlite3.Row) -> BudgetReservation:
        return BudgetReservation(
            invocation_id=row["invocation_id"],
            cycle_id=row["cycle_id"],
            policy_ref=row["policy_ref"],
            state=row["state"],
            reserved_amount=Decimal(row["reserved_amount"]),
            settled_amount=(
                Decimal(row["settled_amount"]) if row["settled_amount"] is not None else None
            ),
            currency=row["currency"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _total(items: tuple[BudgetReservation, ...]) -> Decimal:
        return sum(
            ((
                item.settled_amount
                if item.state is BudgetReservationState.SETTLED
                and item.settled_amount is not None
                else item.reserved_amount
            )
            for item in items),
            start=Decimal("0"),
        )

    @staticmethod
    def _budget_error(detail: str) -> RuntimeInvocationError:
        return RuntimeInvocationError(RuntimeFailureCategory.BUDGET_EXCEEDED, detail)
