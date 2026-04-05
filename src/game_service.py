import os
from datetime import date, timedelta, datetime
from enum import Enum
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import db
import games
from games import GameConfig

load_dotenv()

TZ = ZoneInfo(os.environ["TIMEZONE"])


class ProcessResult(Enum):
    STORED = "stored"        # first valid result for the day, saved to DB
    DUPLICATE = "duplicate"  # valid result but user already submitted today
    IGNORED = "ignored"      # not a recognised game message or wrong puzzle number


# ── Date helpers ──────────────────────────────────────────────────────────────

def local_today() -> date:
    return datetime.now(TZ).date()


def local_date_of(message) -> date:
    return message.created_at.astimezone(TZ).date()


def expected_puzzle_number(for_date: date, config: GameConfig) -> int:
    return (for_date - config.epoch).days


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_result(content: str, config: GameConfig) -> tuple[int, int | None, bool] | None:
    """
    Parse a game result for a specific game config.
    Returns (puzzle_number, attempts, success) or None if not a match.
    attempts is None for failed puzzles (X/6).
    """
    match = config.pattern.search(content)
    if not match:
        return None

    try:
        puzzle_number = int(match.group(1).replace(",", ""))
    except ValueError:
        return None

    attempts_str = match.group(2)
    if attempts_str == "X":
        attempts, success = None, False
    else:
        attempts = int(attempts_str)
        if not 1 <= attempts <= 6:
            return None
        success = True

    # Cross-validate with emoji grid
    grid_lines = [
        line.strip()
        for line in content.splitlines()
        if any(e in line for e in config.grid_emojis)
    ]
    if grid_lines:
        # Each row must have exactly grid_width cells
        if any(
            len([c for c in line if c in config.grid_emojis]) != config.grid_width
            for line in grid_lines
        ):
            return None

        # Row count must match reported attempts
        if attempts is not None and len(grid_lines) != attempts:
            return None

        # Last row must be all-green if success, not all-green if failed
        cells = [c for c in grid_lines[-1] if c in config.grid_emojis]
        all_green = bool(cells) and all(c == "🟩" for c in cells)
        if success and not all_green:
            return None
        if not success and all_green:
            return None

    return puzzle_number, attempts, success


def detect_game(content: str) -> tuple[GameConfig, int, int | None, bool] | None:
    """Try all game configs in order, return first match."""
    for config in games.ALL_GAMES:
        result = parse_result(content, config)
        if result is not None:
            return (config, *result)
    return None


# ── Core logic ────────────────────────────────────────────────────────────────

def process_message(message) -> tuple[ProcessResult, str | None, int | None]:
    """
    Detect, validate and store a game result from a Discord message.
    Returns (ProcessResult, game_key, attempts).
    game_key and attempts are None when IGNORED.
    """
    if message.author.bot:
        return ProcessResult.IGNORED, None, None

    detected = detect_game(message.content)
    if detected is None:
        return ProcessResult.IGNORED, None, None

    config, puzzle_number, attempts, success = detected
    msg_date = local_date_of(message)

    if puzzle_number != expected_puzzle_number(msg_date, config):
        return ProcessResult.IGNORED, None, None

    stored = db.store_result(
        str(message.author.id),
        message.author.display_name,
        config.key,
        msg_date,
        puzzle_number,
        attempts,
        success,
    )
    return (ProcessResult.STORED if stored else ProcessResult.DUPLICATE), config.key, attempts


def calculate_streak(user_id: str, game_key: str) -> int:
    """Current streak for a user in a specific game."""
    today = local_today()
    dates = db.get_successful_dates(user_id, game_key)

    if not dates:
        return 0

    yesterday = today - timedelta(days=1)
    if today in dates:
        check = today
    elif yesterday in dates:
        check = yesterday
    else:
        return 0

    streak = 0
    while check in dates:
        streak += 1
        check -= timedelta(days=1)
    return streak


def calculate_best_streak(user_id: str, game_key: str) -> int:
    """Longest consecutive successful days ever for a user in a specific game."""
    dates = sorted(db.get_successful_dates(user_id, game_key))
    if not dates:
        return 0
    best = current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
            if current > best:
                best = current
        else:
            current = 1
    return best


def get_user_stats(user_id: str) -> dict[str, dict]:
    """Returns stats per game for a user, keyed by game_key."""
    result = {}
    for config in games.ALL_GAMES:
        total, wins = db.get_game_counts(user_id, config.key)
        result[config.key] = {
            "display_name": config.display_name,
            "total": total,
            "wins": wins,
            "win_rate": wins / total if total else 0.0,
            "avg_attempts": db.get_average_attempts(user_id, config.key),
            "streak": calculate_streak(user_id, config.key),
            "best_streak": calculate_best_streak(user_id, config.key),
        }
    return result


def get_rankings(game_key: str) -> list[tuple[str, int, float | None]]:
    """Returns [(username, streak, avg_attempts)] for a game, sorted by streak descending."""
    users = db.get_all_users(game_key)
    rows = [
        (username, calculate_streak(user_id, game_key), db.get_average_attempts(user_id, game_key))
        for user_id, username in users
    ]
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def get_at_risk_users(game_key: str) -> list[tuple[str, str]]:
    """Returns (user_id, username) for users whose streak will break at midnight."""
    today = local_today()
    yesterday = today - timedelta(days=1)
    return db.get_users_at_risk(game_key, yesterday, today)
