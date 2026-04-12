import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class GameConfig:
    key: str
    display_name: str
    epoch: date | None
    max_attempts: int | None = 6
    pattern: re.Pattern | None = None
    grid_emojis: frozenset = frozenset()
    grid_width: int = 0


def _epoch(ref_date: date, ref_puzzle: int) -> date:
    return ref_date - timedelta(days=ref_puzzle)


# ── Standard games (use the generic regex parser in game_service) ─────────────

WORDLE = GameConfig(
    key="wordle",
    display_name="Wordle",
    epoch=date(2021, 6, 19),
    pattern=re.compile(r"^\s*Wordle\s+([\d,.]+)\s+([X\d])/6", re.MULTILINE),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
    grid_width=5,
)

ROWORDLE = GameConfig(
    key="rowordle",
    display_name="RoWordle",
    epoch=_epoch(date(2026, 4, 5), 1555),
    pattern=re.compile(r"🇷🇴\s*Wordle-RO\s+([\d,]+)\s+([X\d])/6"),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
    grid_width=5,
)

NERDLE = GameConfig(
    key="nerdle",
    display_name="Nerdle",
    epoch=_epoch(date(2026, 4, 5), 1537),
    pattern=re.compile(r"nerdlegame\s+([\d,]+)\s+([X\d])/6"),
    grid_emojis=frozenset({"⬛", "🟪", "🟩"}),
    grid_width=8,
)

# ── Custom-parsed games (have dedicated parsers in game_service) ──────────────

OWDLE_EPOCH = date(2020, 1, 1)

QUORDLE = GameConfig(
    key="quordle",
    display_name="Quordle",
    epoch=_epoch(date(2026, 4, 6), 1533),
    max_attempts=9,
)

OWDLE_HERO = GameConfig(
    key="owdle_hero",
    display_name="Owdle Hero",
    epoch=OWDLE_EPOCH,
    max_attempts=None,
)

OWDLE_CONVERSATION = GameConfig(
    key="owdle_conversation",
    display_name="Owdle Conversation",
    epoch=OWDLE_EPOCH,
    max_attempts=None,
)

DOCTORDLE = GameConfig(
    key="doctordle",
    display_name="Doctordle",
    epoch=_epoch(date(2026, 4, 6), 264),
)

POLYGONLE = GameConfig(
    key="polygonle",
    display_name="Polygonle",
    epoch=_epoch(date(2026, 4, 11), 1350),
    pattern=re.compile(r"^#Polygonle (\d+) ([X\d])/6\S*", re.MULTILINE),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
)

POLYGONLE_MINI = GameConfig(
    key="polygonle_mini",
    display_name="PolygonleMini",
    epoch=_epoch(date(2026, 4, 11), 1104),
    pattern=re.compile(r"^#PolygonleMini (\d+) ([X\d])/6\S*", re.MULTILINE),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
    grid_width=5,
)


ALL_GAMES: list[GameConfig] = [
    WORDLE, ROWORDLE, NERDLE,
    QUORDLE,
    OWDLE_HERO, OWDLE_CONVERSATION,
    DOCTORDLE,
    POLYGONLE, POLYGONLE_MINI,
]
GAMES_BY_KEY: dict[str, GameConfig] = {g.key: g for g in ALL_GAMES}
