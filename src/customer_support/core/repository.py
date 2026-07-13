"""Database access for the customer support business layer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import sqlite3
from pathlib import Path
from typing import Iterator

from customer_support.core.database import DEFAULT_DB_PATH, get_connection
from customer_support.core.models import AuditEntry


class SupportRepository:
    """Small repository that owns all SQL statements."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN")
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def get_customer(self, customer_id: str) -> sqlite3.Row | None:
        connection = self.connect()
        try:
            return self.get_customer_for_update(connection, customer_id)
        finally:
            connection.close()

    def get_order(self, order_id: str) -> sqlite3.Row | None:
        connection = self.connect()
        try:
            return self.get_order_for_update(connection, order_id)
        finally:
            connection.close()

    def get_customer_for_update(
        self, connection: sqlite3.Connection, customer_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT customer_id, name, email, loyalty_tier
            FROM customers
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

    def get_order_for_update(
        self, connection: sqlite3.Connection, order_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT order_id, customer_id, amount, status, payment_status, created_at
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

    def get_processed_response(
        self, connection: sqlite3.Connection, request_id: str
    ) -> str | None:
        row = connection.execute(
            """
            SELECT response_json
            FROM processed_requests
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()
        return row["response_json"] if row else None

    def save_processed_response(
        self,
        connection: sqlite3.Connection,
        request_id: str,
        operation: str,
        response_json: str,
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO processed_requests
                (request_id, operation, response_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (request_id, operation, response_json, created_at.isoformat()),
        )

    def insert_refund(
        self,
        connection: sqlite3.Connection,
        request_id: str,
        customer_id: str,
        order_id: str,
        amount: float,
        reason: str,
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO refunds
                (request_id, customer_id, order_id, amount, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (request_id, customer_id, order_id, amount, reason, created_at.isoformat()),
        )

    def insert_store_credit(
        self,
        connection: sqlite3.Connection,
        request_id: str,
        customer_id: str,
        amount: float,
        reason: str,
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO store_credit
                (request_id, customer_id, amount, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, customer_id, amount, reason, created_at.isoformat()),
        )

    def insert_audit_entry(
        self, connection: sqlite3.Connection, entry: AuditEntry
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs
                (timestamp, action, request_id, customer_id, order_id, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(),
                entry.action,
                entry.request_id,
                entry.customer_id,
                entry.order_id,
                entry.amount,
                entry.status,
            ),
        )

    def list_audit_logs(self) -> list[sqlite3.Row]:
        connection = self.connect()
        try:
            return connection.execute(
                """
                SELECT timestamp, action, request_id, customer_id, order_id, amount, status
                FROM audit_logs
                ORDER BY timestamp ASC, id ASC
                """
            ).fetchall()
        finally:
            connection.close()
