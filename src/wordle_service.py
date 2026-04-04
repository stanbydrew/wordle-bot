import os
import re
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import db

load_dotenv()

TZ = ZoneInfo(os.environ["TIMEZONE"])
WORDLE_EPOCH = date(2021, 6, 19)  # (date - epoch).days == puzzle number; #1750 = April 4, 2026


# ── Date helpers ──────────────────────────────────────────────────────────────

def local_today() -> date:
    return datetime.now(TZ).date()


def local_date_of(message) -> date:
    return message.created_at.astimezone(TZ).date()


def expected_puzzle_number(for_date: date) -> int:
    return (for_date - WORDLE_EPOCH).days


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_wordle(content: str) -> tuple[int, int | None, bool] | None:
    """
    Parses a Wordle result from a message string.
    Returns (puzzle_number, attempts, success) or None if not a valid Wordle post.
    attempts is None when the puzzle was failed (X/6).
    Cross-validates the emoji grid against the header score.
    """
    match = re.search(r"Wordle\s+([\d,]+)\s+([X\d])/6", content)
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

    # Cross-validate with emoji grid: last row must be all-green iff success
    grid_lines = [
        line.strip()
        for line in content.splitlines()
        if re.search(r"[⬛⬜🟨🟩]", line)
    ]
    if grid_lines:
        cells = [c for c in grid_lines[-1] if c in "⬛⬜🟨🟩"]
        all_green = bool(cells) and all(c == "🟩" for c in cells)
        if success and not all_green:
            return None
        if not success and all_green:
            return None

    return puzzle_number, attempts, success


# ── Core logic ────────────────────────────────────────────────────────────────

def process_message(message) -> bool:
    """
    Validate and store a Wordle result from a Discord message.
    Returns True if this is the first valid result for this user today (bot should react).
    Returns False for non-Wordle messages, wrong puzzle number, or duplicate submissions.
    """
    if message.author.bot:
        return False

    parsed = parse_wordle(message.content)
    if parsed is None:
        return False

    puzzle_number, attempts, success = parsed
    msg_date = local_date_of(message)

    if puzzle_number != expected_puzzle_number(msg_date):
        return False

    return db.store_result(
        str(message.author.id),
        message.author.display_name,
        msg_date,
        puzzle_number,
        attempts,
        success,
    )


def calculate_streak(user_id: str) -> int:
    """
    Current streak for a user: consecutive successful days ending today or yesterday.
    Streak is still considered alive if the user hasn't posted today yet (yesterday was last day).
    """
    today = local_today()
    dates = db.get_successful_dates(user_id)

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


def get_rankings() -> list[tuple[str, int]]:
    """Returns [(username, streak)] for all users, sorted by streak descending."""
    users = db.get_all_users()
    rows = [(username, calculate_streak(user_id)) for user_id, username in users]
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def get_at_risk_users() -> list[tuple[str, str]]:
    """
    Returns (user_id, username) for users whose streak will break at midnight
    (completed yesterday, not yet completed today).
    """
    today = local_today()
    yesterday = today - timedelta(days=1)
    return db.get_users_at_risk(yesterday, today)
