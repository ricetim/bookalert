import sqlite3
from pathlib import Path
from typing import Optional


def get_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS books (
            isbn         TEXT    PRIMARY KEY,
            title        TEXT    NOT NULL,
            author       TEXT    NOT NULL DEFAULT '',
            target_price REAL    NOT NULL,
            added_at     TEXT    NOT NULL DEFAULT (datetime('now')),
            last_checked TEXT,
            active       INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn         TEXT    NOT NULL REFERENCES books(isbn),
            checked_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            lowest_price REAL,
            available    INTEGER NOT NULL DEFAULT 0,
            condition    TEXT    NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_price_history_isbn
            ON price_history (isbn, checked_at DESC);
    """)
    # Migrate existing DBs that predate the condition column
    try:
        conn.execute("ALTER TABLE price_history ADD COLUMN condition TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


def add_book(conn: sqlite3.Connection, isbn: str, title: str, author: str, target_price: float) -> None:
    conn.execute(
        """
        INSERT INTO books (isbn, title, author, target_price, added_at, active)
        VALUES (?, ?, ?, ?, datetime('now'), 1)
        ON CONFLICT(isbn) DO UPDATE SET
            title        = excluded.title,
            author       = excluded.author,
            target_price = excluded.target_price,
            added_at     = datetime('now'),
            active       = 1
        """,
        (isbn, title, author, target_price),
    )
    conn.commit()


def remove_book(conn: sqlite3.Connection, isbn: str) -> bool:
    cur = conn.execute(
        "UPDATE books SET active = 0 WHERE isbn = ? AND active = 1",
        (isbn,),
    )
    conn.commit()
    return cur.rowcount > 0


def list_books(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT b.*, ph.lowest_price AS current_price, ph.checked_at AS price_as_of,
               ph.condition AS current_condition
        FROM books b
        LEFT JOIN (
            SELECT isbn, lowest_price, checked_at, condition FROM price_history
            WHERE id IN (SELECT MAX(id) FROM price_history GROUP BY isbn)
        ) ph ON ph.isbn = b.isbn
        WHERE b.active = 1 ORDER BY b.added_at DESC
    """).fetchall()


def get_active_books(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM books WHERE active = 1"
    ).fetchall()


def record_price(
    conn: sqlite3.Connection,
    isbn: str,
    lowest_price: Optional[float],
    target_price: float,
    condition: str = "",
) -> bool:
    available = lowest_price is not None and lowest_price <= target_price
    conn.execute(
        """
        INSERT INTO price_history (isbn, checked_at, lowest_price, available, condition)
        VALUES (?, datetime('now'), ?, ?, ?)
        """,
        (isbn, lowest_price, int(available), condition),
    )
    conn.execute(
        "UPDATE books SET last_checked = datetime('now') WHERE isbn = ?",
        (isbn,),
    )
    conn.commit()
    return available


def get_history(conn: sqlite3.Connection, isbn: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM price_history
        WHERE isbn = ?
        ORDER BY checked_at DESC
        LIMIT 100
        """,
        (isbn,),
    ).fetchall()


def get_alerts(conn: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    """All price checks where price met target (available=1), newest first."""
    return conn.execute("""
        SELECT ph.id, ph.isbn, ph.checked_at, ph.lowest_price,
               ph.condition, b.title, b.author, b.target_price
        FROM price_history ph
        JOIN books b ON b.isbn = ph.isbn
        WHERE ph.available = 1
        ORDER BY ph.checked_at DESC LIMIT ?
    """, (limit,)).fetchall()
