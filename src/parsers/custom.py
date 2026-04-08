import re
from datetime import date

import games

# ── Quordle ───────────────────────────────────────────────────────────────────
# 2×2 grid of number-emojis (solved) or 🟥 (failed)

_QUORDLE_HEADER = re.compile(r"Daily Quordle\s+(\d+)")
_QUORDLE_CELL = re.compile(r"🟥|[1-9]\ufe0f\u20e3")


def parse_quordle(content: str) -> tuple[int, int | None, bool] | None:
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


# ── Owdle ─────────────────────────────────────────────────────────────────────
# Date-based; convert the result date to days-since-epoch so existing
# puzzle-number validation works without any changes to process_message.

_OWDLE_HERO_HEADER = re.compile(r"Owdle Hero (\d{4}-\d{2}-\d{2}) ([✅❌]) \((\d+) tries\)")
_OWDLE_CONV_HEADER = re.compile(r"Owdle Conversation (\d{4}-\d{2}-\d{2}) ([✅❌]) \((\d+) tries\)")


def _parse_owdle(content: str, header_pattern: re.Pattern) -> tuple[int, int | None, bool] | None:
    m = header_pattern.search(content)
    if not m:
        return None
    game_date = date.fromisoformat(m.group(1))
    puzzle_number = (game_date - games.OWDLE_EPOCH).days
    success = m.group(2) == "✅"
    attempts = int(m.group(3)) if success else None
    return puzzle_number, attempts, success


def parse_owdle_hero(content: str) -> tuple[int, int | None, bool] | None:
    return _parse_owdle(content, _OWDLE_HERO_HEADER)


def parse_owdle_conversation(content: str) -> tuple[int, int | None, bool] | None:
    return _parse_owdle(content, _OWDLE_CONV_HEADER)


# ── Doctordle ─────────────────────────────────────────────────────────────────
# Single grid line: 🏥 followed by 🟥 (wrong) / 🟩 (correct) / ⬛ (remaining)

_DOCTORDLE_HEADER = re.compile(r"Doctordle #(\d+)")
_DOCTORDLE_CELLS = {"🟥", "🟩", "⬛"}


def parse_doctordle(content: str) -> tuple[int, int | None, bool] | None:
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


# ── Registry ──────────────────────────────────────────────────────────────────

CUSTOM_PARSERS: dict[str, callable] = {
    "quordle": parse_quordle,
    "owdle_hero": parse_owdle_hero,
    "owdle_conversation": parse_owdle_conversation,
    "doctordle": parse_doctordle,
}
