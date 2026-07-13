"""SQLite initialization and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("customer_support.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    loyalty_tier TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS store_credit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS processed_requests (
    request_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    request_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    order_id TEXT,
    amount REAL NOT NULL,
    status TEXT NOT NULL
);
"""


SAMPLE_CUSTOMERS = [
    ("cust_1001", "Avery Johnson", "avery@example.com", "gold"),
    ("cust_1002", "Mina Patel", "mina@example.com", "silver"),
    ("cust_1003", "Jordan Lee", "jordan@example.com", "platinum"),
]

SAMPLE_ORDERS = [
    ("ord_5001", "cust_1001", 129.99, "delivered", "paid", "2026-05-03T10:15:00"),
    ("ord_5002", "cust_1002", 42.5, "delivered", "paid", "2026-05-09T14:30:00"),
    ("ord_5003", "cust_1003", 219.0, "shipped", "paid", "2026-05-18T09:45:00"),
]


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a configured SQLite connection, creating schema and seed data."""
    path = Path(db_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create tables and insert sample data if they are not present."""
    connection.executescript(SCHEMA)
    connection.executemany(
        """
        INSERT OR IGNORE INTO customers
            (customer_id, name, email, loyalty_tier)
        VALUES (?, ?, ?, ?)
        """,
        SAMPLE_CUSTOMERS,
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO orders
            (order_id, customer_id, amount, status, payment_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        SAMPLE_ORDERS,
    )
    connection.commit()
