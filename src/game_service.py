import os
import re
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


# ── Standard parser ──────────────────────────────────────────────────────────

def parse_result(content: str, config: GameConfig) -> tuple[int, int | None, bool] | None:
    """
    Parse a game result using the standard regex+grid pattern.
    Returns (puzzle_number, attempts, success) or None if not a match.
    attempts is None for failed puzzles (X/6).
    """
    match = config.pattern.search(content)
    if not match:
        return None

    try:
        puzzle_number = int(match.group(1).replace(",", "").replace(".", ""))
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

    # Cross-validate with emoji grid — only scan lines after the header match
    # to avoid picking up grid rows from other games in the same message.
    grid_lines = []
    for line in content[match.end():].splitlines():
        stripped = line.strip()
        if any(e in stripped for e in config.grid_emojis):
            grid_lines.append(stripped)
        elif grid_lines:
            break  # stop at first non-grid line after grid has started
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


# ── Custom parsers ───────────────────────────────────────────────────────────

_CUSTOM_PARSERS: dict[str, callable] = {}


def _custom_parser(key: str):
    """Register a custom parser for a game key."""
    def decorator(fn):
        _CUSTOM_PARSERS[key] = fn
        return fn
    return decorator


# Quordle — 2×2 grid of number-emojis (solved) or 🟥 (failed)
_QUORDLE_HEADER = re.compile(r"Daily Quordle\s+(\d+)")
_QUORDLE_CELL = re.compile(r"🟥|[1-9]\ufe0f\u20e3")


@_custom_parser("quordle")
def _parse_quordle(content: str):
    m = _QUORDLE_HEADER.search(content)
    if not m:
        return None
    puzzle_number = int(m.group(1))
    cells = _QUORDLE_CELL.findall(content[m.end():])
    if len(cells) < 4:
        return None
    cells = cells[:4]
    if any(c == "🟥" for c in cells):
        return puzzle_number, None, False
    return puzzle_number, max(int(c[0]) for c in cells), True


# Owdle — date-based; convert the result date to days-since-epoch so existing
# puzzle-number validation works without any changes to process_message.
_OWDLE_HERO_HEADER = re.compile(r"Owdle Hero (\d{4}-\d{2}-\d{2}) ([✅❌]) \((\d+) tries\)")
_OWDLE_CONV_HEADER = re.compile(r"Owdle Conversation (\d{4}-\d{2}-\d{2}) ([✅❌]) \((\d+) tries\)")


def _parse_owdle(content: str, header_pattern: re.Pattern):
    m = header_pattern.search(content)
    if not m:
        return None
    game_date = date.fromisoformat(m.group(1))
    puzzle_number = (game_date - games.OWDLE_EPOCH).days
    success = m.group(2) == "✅"
    attempts = int(m.group(3)) if success else None
    return puzzle_number, attempts, success


@_custom_parser("owdle_hero")
def _parse_owdle_hero(content: str):
    return _parse_owdle(content, _OWDLE_HERO_HEADER)


@_custom_parser("owdle_conversation")
def _parse_owdle_conversation(content: str):
    return _parse_owdle(content, _OWDLE_CONV_HEADER)


# Doctordle — single grid line: 🏥 followed by 🟥 (wrong) / 🟩 (correct) / ⬛ (remaining)
_DOCTORDLE_HEADER = re.compile(r"Doctordle #(\d+)")
_DOCTORDLE_CELLS = {"🟥", "🟩", "⬛"}


@_custom_parser("doctordle")
def _parse_doctordle(content: str):
    m = _DOCTORDLE_HEADER.search(content)
    if not m:
        return None
    puzzle_number = int(m.group(1))
    grid_line = None
    for line in content[m.end():].splitlines():
        stripped = line.strip()
        if stripped.startswith("🏥"):
            grid_line = stripped
            break
    if not grid_line:
        return None
    cells = [c for c in grid_line.split() if c in _DOCTORDLE_CELLS]
    active = [c for c in cells if c != "⬛"]
    if not active:
        return None
    success = active[-1] == "🟩"
    attempts = len(active) if success else None
    return puzzle_number, attempts, success


# ── Detection ────────────────────────────────────────────────────────────────

def detect_all_games(content: str) -> list[tuple[GameConfig, int, int | None, bool]]:
    """Try all game configs, return all matches found in the message."""
    results = []
    for config in games.ALL_GAMES:
        parser = _CUSTOM_PARSERS.get(config.key)
        result = parser(content) if parser else parse_result(content, config)
        if result is not None:
            results.append((config, *result))
    return results


# ── Core logic ────────────────────────────────────────────────────────────────

def process_message(message) -> list[tuple[ProcessResult, str | None, int | None]]:
    """
    Detect, validate and store all game results from a Discord message.
    Returns a list of (ProcessResult, game_key, attempts) — one entry per recognised game.
    Returns [(IGNORED, None, None)] when no games are found.
    """
    if message.author.bot:
        return [(ProcessResult.IGNORED, None, None)]

    detected = detect_all_games(message.content)
    if not detected:
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


def calculate_streak(user_id: str, game_key: str) -> int:
    """Current streak for a user in a specific game."""
    today = local_today()
    dates = db.get_successful_dates(user_id, game_key)

    if not dates:
        return 0

    yesterday = today - timedelta(days=1)
    if today in dates:
        check = today
    elif yesterday in dates and not db.has_result(user_id, game_key, today):
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
    """Returns [(username, streak, avg_attempts)] for a game, sorted by streak descending."""
    users = db.get_all_users(game_key)
    rows = [
        (username, calculate_streak(user_id, game_key), db.get_average_attempts(user_id, game_key))
        for user_id, username in users
    ]
    rows.sort(key=lambda x: (-x[1], x[2] if x[2] is not None else float("inf")))
    return rows


def get_at_risk_users(game_key: str) -> list[tuple[str, str]]:
    """Returns (user_id, username) for users whose streak will break at midnight."""
    today = local_today()
    yesterday = today - timedelta(days=1)
    return db.get_users_at_risk(game_key, yesterday, today)
