import sqlite3
from datetime import date

DB_PATH = "wordle.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wordle_results (
                user_id       TEXT NOT NULL,
                username      TEXT NOT NULL,
                date          TEXT NOT NULL,
                puzzle_number INTEGER NOT NULL,
                attempts      INTEGER,
                success       INTEGER NOT NULL,
                PRIMARY KEY (user_id, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)


# ── Meta ──────────────────────────────────────────────────────────────────────

def get_meta(key: str) -> str | None:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))


def get_last_message_id() -> int | None:
    value = get_meta("last_message_id")
    return int(value) if value else None


def set_last_message_id(message_id: int):
    set_meta("last_message_id", str(message_id))


# ── Results ───────────────────────────────────────────────────────────────────

def store_result(
    user_id: str,
    username: str,
    result_date: date,
    puzzle_number: int,
    attempts: int | None,
    success: bool,
) -> bool:
    """
    Insert a Wordle result. Returns True if this was a new insert
    (first result for this user today), False if the slot was already filled.
    On duplicate: only the username is updated, the original result is kept.
    """
    with _conn() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO wordle_results
                (user_id, username, date, puzzle_number, attempts, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, result_date.isoformat(), puzzle_number, attempts, int(success)))

        if cursor.rowcount == 1:
            return True

        # Duplicate — keep result, refresh username only
        conn.execute(
            "UPDATE wordle_results SET username = ? WHERE user_id = ? AND date = ?",
            (username, user_id, result_date.isoformat()),
        )
        return False


def get_all_users() -> list[tuple[str, str]]:
    """Returns (user_id, username) for all users, using their most recent username."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT wr.user_id, wr.username
            FROM wordle_results wr
            WHERE wr.date = (
                SELECT MAX(date) FROM wordle_results WHERE user_id = wr.user_id
            )
            GROUP BY wr.user_id
        """).fetchall()
    return [(r["user_id"], r["username"]) for r in rows]


def get_successful_dates(user_id: str) -> set[date]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT date FROM wordle_results
            WHERE user_id = ? AND success = 1
        """, (user_id,)).fetchall()
    return {date.fromisoformat(r["date"]) for r in rows}


def get_users_at_risk(yesterday: date, today: date) -> list[tuple[str, str]]:
    """
    Returns (user_id, username) for users who completed yesterday (active streak)
    but have not completed today — their streak will break at midnight.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT wr.user_id, wr.username
            FROM wordle_results wr
            WHERE wr.date = ? AND wr.success = 1
            AND NOT EXISTS (
                SELECT 1 FROM wordle_results
                WHERE user_id = wr.user_id AND date = ? AND success = 1
            )
        """, (yesterday.isoformat(), today.isoformat())).fetchall()
    return [(r["user_id"], r["username"]) for r in rows]
