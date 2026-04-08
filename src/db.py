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
            CREATE TABLE IF NOT EXISTS game_results (
                user_id       TEXT NOT NULL,
                username      TEXT NOT NULL,
                game          TEXT NOT NULL DEFAULT 'wordle',
                date          TEXT NOT NULL,
                puzzle_number INTEGER NOT NULL,
                attempts      INTEGER,
                success       INTEGER NOT NULL,
                PRIMARY KEY (user_id, game, date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Migrate old wordle_results table if it exists
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "wordle_results" in tables:
            conn.execute("""
                INSERT OR IGNORE INTO game_results
                    (user_id, username, game, date, puzzle_number, attempts, success)
                SELECT user_id, username, 'wordle', date, puzzle_number, attempts, success
                FROM wordle_results
            """)
            conn.execute("DROP TABLE wordle_results")


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
    game: str,
    result_date: date,
    puzzle_number: int,
    attempts: int | None,
    success: bool,
) -> bool:
    """
    Insert a game result. Returns True if this was a new insert
    (first result for this user/game today), False if the slot was already filled.
    On duplicate: only the username is updated, the original result is kept.
    """
    with _conn() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO game_results
                (user_id, username, game, date, puzzle_number, attempts, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, game, result_date.isoformat(), puzzle_number, attempts, int(success)))

        if cursor.rowcount == 1:
            return True

        # Duplicate — keep result, refresh username only
        conn.execute(
            "UPDATE game_results SET username = ? WHERE user_id = ? AND game = ? AND date = ?",
            (username, user_id, game, result_date.isoformat()),
        )
        return False


def get_all_users(game: str) -> list[tuple[str, str]]:
    """Returns (user_id, username) for all users who have played a game, using their most recent username."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT gr.user_id, gr.username
            FROM game_results gr
            WHERE gr.game = ?
            AND gr.date = (
                SELECT MAX(date) FROM game_results
                WHERE user_id = gr.user_id AND game = ?
            )
            GROUP BY gr.user_id
        """, (game, game)).fetchall()
    return [(r["user_id"], r["username"]) for r in rows]


def get_successful_dates(user_id: str, game: str) -> set[date]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT date FROM game_results
            WHERE user_id = ? AND game = ? AND success = 1
        """, (user_id, game)).fetchall()
    return {date.fromisoformat(r["date"]) for r in rows}


def get_game_counts(user_id: str, game: str) -> tuple[int, int]:
    """Returns (total_games, total_wins) for a user in a specific game."""
    with _conn() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as total, SUM(success) as wins
            FROM game_results WHERE user_id = ? AND game = ?
        """, (user_id, game)).fetchone()
    return (row["total"] or 0, row["wins"] or 0)


def get_average_attempts(user_id: str, game: str) -> float | None:
    with _conn() as conn:
        row = conn.execute("""
            SELECT AVG(attempts) FROM game_results
            WHERE user_id = ? AND game = ? AND success = 1
        """, (user_id, game)).fetchone()
    return row[0] if row and row[0] is not None else None


def has_result(user_id: str, game: str, result_date: date) -> bool:
    """Returns True if the user has any result (win or loss) for the given date."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM game_results WHERE user_id = ? AND game = ? AND date = ?",
            (user_id, game, result_date.isoformat()),
        ).fetchone()
    return row is not None


def get_all_successful_dates(game: str) -> dict[str, set[date]]:
    """Returns {user_id: set of successful dates} for all users in a game. Single query."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT user_id, date FROM game_results WHERE game = ? AND success = 1
        """, (game,)).fetchall()
    result: dict[str, set[date]] = {}
    for r in rows:
        result.setdefault(r["user_id"], set()).add(date.fromisoformat(r["date"]))
    return result


def get_all_average_attempts(game: str) -> dict[str, float | None]:
    """Returns {user_id: avg_attempts} for all users in a game. Single query."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT user_id, AVG(attempts) as avg_att FROM game_results
            WHERE game = ? AND success = 1
            GROUP BY user_id
        """, (game,)).fetchall()
    return {r["user_id"]: r["avg_att"] for r in rows}


def get_users_with_result(game: str, result_date: date) -> set[str]:
    """Returns user_ids who have any result (win or loss) for the given game and date."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT user_id FROM game_results WHERE game = ? AND date = ?
        """, (game, result_date.isoformat())).fetchall()
    return {r["user_id"] for r in rows}


def get_users_at_risk(game: str, yesterday: date, today: date) -> list[tuple[str, str]]:
    """
    Returns (user_id, username) for users who completed yesterday (active streak)
    but have not completed today — their streak will break at midnight.
    """
    with _conn() as conn:
        rows = conn.execute("""
            SELECT gr.user_id, gr.username
            FROM game_results gr
            WHERE gr.game = ? AND gr.date = ? AND gr.success = 1
            AND NOT EXISTS (
                SELECT 1 FROM game_results
                WHERE user_id = gr.user_id AND game = ? AND date = ? AND success = 1
            )
        """, (game, yesterday.isoformat(), game, today.isoformat())).fetchall()
    return [(r["user_id"], r["username"]) for r in rows]
