"""Audit logging helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

from customer_support.core.models import AuditEntry
from customer_support.core.repository import SupportRepository


class AuditLogger:
    """Writes and reads concise audit entries."""

    def __init__(self, repository: SupportRepository) -> None:
        self.repository = repository

    def log(
        self,
        connection: sqlite3.Connection,
        *,
        action: str,
        request_id: str,
        customer_id: str,
        order_id: str | None,
        amount: float,
        status: str,
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            action=action,
            request_id=request_id,
            customer_id=customer_id,
            order_id=order_id,
            amount=amount,
            status=status,
        )
        self.repository.insert_audit_entry(connection, entry)
        return entry

    def get_audit_logs(self) -> list[AuditEntry]:
        return [
            AuditEntry(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                action=row["action"],
                request_id=row["request_id"],
                customer_id=row["customer_id"],
                order_id=row["order_id"],
                amount=row["amount"],
                status=row["status"],
            )
            for row in self.repository.list_audit_logs()
        ]
