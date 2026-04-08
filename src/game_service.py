import logging
from datetime import date, timedelta, datetime
from enum import Enum

import db
import games
from config import TZ
from games import GameConfig
from parsers import detect_all_games

logger = logging.getLogger(__name__)

# Emojis that hint a message might be a game result
_GAME_HINT_EMOJIS = frozenset({"🟩", "🟨", "⬛", "⬜", "🟪", "🟥", "🏥"})


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


# ── Core logic ────────────────────────────────────────────────────────────────

def process_message(message) -> list[tuple[ProcessResult, str | None, int | None]]:
    """
    Detect, validate and store all game results from a Discord message.
    Returns a list of (ProcessResult, game_key, attempts) — one entry per recognised game.
    Returns [(IGNORED, None, None)] when no games are found or when the message looks like
    a game but no parser matched (parse failure is logged as a warning in that case).
    """
    if message.author.bot:
        return [(ProcessResult.IGNORED, None, None)]

    detected = detect_all_games(message.content)
    if not detected:
        if any(e in message.content for e in _GAME_HINT_EMOJIS):
            logger.warning(
                "Unrecognised game message from %s (id=%s): %.200s",
                message.author.display_name,
                message.author.id,
                message.content,
            )
        return [(ProcessResult.IGNORED, None, None)]

    msg_date = local_date_of(message)
    results = []

    for config, puzzle_number, attempts, success in detected:
        if puzzle_number != expected_puzzle_number(msg_date, config):
            continue

        stored = db.store_result(
            str(message.author.id),
            message.author.display_name,
            config.key,
            msg_date,
            puzzle_number,
            attempts,
            success,
        )
        results.append(
            (ProcessResult.STORED if stored else ProcessResult.DUPLICATE, config.key, attempts)
        )

    return results if results else [(ProcessResult.IGNORED, None, None)]


# ── Streak helpers ────────────────────────────────────────────────────────────

def _calculate_streak_from_data(
    successful_dates: set[date],
    has_today_result: bool,
    today: date,
) -> int:
    """Compute streak from pre-fetched data (no DB calls)."""
    if not successful_dates:
        return 0
    yesterday = today - timedelta(days=1)
    if today in successful_dates:
        check = today
    elif yesterday in successful_dates and not has_today_result:
        check = yesterday
    else:
        return 0
    streak = 0
    while check in successful_dates:
        streak += 1
        check -= timedelta(days=1)
    return streak


def calculate_streak(user_id: str, game_key: str) -> int:
    """Current streak for a user in a specific game."""
    today = local_today()
    successful_dates = db.get_successful_dates(user_id, game_key)
    has_today = db.has_result(user_id, game_key, today)
    return _calculate_streak_from_data(successful_dates, has_today, today)


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
            "max_attempts": config.max_attempts,
            "total": total,
            "wins": wins,
            "win_rate": wins / total if total else 0.0,
            "avg_attempts": db.get_average_attempts(user_id, config.key),
            "streak": calculate_streak(user_id, config.key),
            "best_streak": calculate_best_streak(user_id, config.key),
        }
    return result


def get_rankings(game_key: str) -> list[tuple[str, int, float | None]]:
    """Returns [(username, streak, avg_attempts)] for a game, sorted by streak descending.
    Uses batch DB queries to avoid N+1 per user.
    """
    users = db.get_all_users(game_key)
    if not users:
        return []

    today = local_today()
    all_dates = db.get_all_successful_dates(game_key)
    all_avgs = db.get_all_average_attempts(game_key)
    users_with_today = db.get_users_with_result(game_key, today)

    rows = []
    for user_id, username in users:
        successful_dates = all_dates.get(user_id, set())
        has_today = user_id in users_with_today
        streak = _calculate_streak_from_data(successful_dates, has_today, today)
        avg = all_avgs.get(user_id)
        rows.append((username, streak, avg))

    rows.sort(key=lambda x: (-x[1], x[2] if x[2] is not None else float("inf")))
    return rows


def get_at_risk_users(game_key: str) -> list[tuple[str, str]]:
    """Returns (user_id, username) for users whose streak will break at midnight."""
    today = local_today()
    yesterday = today - timedelta(days=1)
    return db.get_users_at_risk(game_key, yesterday, today)
