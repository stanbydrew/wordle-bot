import re
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class GameConfig:
    key: str
    display_name: str
    pattern: re.Pattern
    grid_emojis: frozenset
    grid_width: int
    epoch: date


def _epoch(ref_date: date, ref_puzzle: int) -> date:
    return ref_date - timedelta(days=ref_puzzle)


WORDLE = GameConfig(
    key="wordle",
    display_name="Wordle",
    pattern=re.compile(r"Wordle\s+([\d,]+)\s+([X\d])/6"),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
    grid_width=5,
    epoch=date(2021, 6, 19),
)

ROWORDLE = GameConfig(
    key="rowordle",
    display_name="RoWordle",
    pattern=re.compile(r"🇷🇴\s*Wordle-RO\s+([\d,]+)\s+([X\d])/6"),
    grid_emojis=frozenset({"⬛", "⬜", "🟨", "🟩"}),
    grid_width=5,
    epoch=_epoch(date(2026, 4, 5), 1555),
)

NERDLE = GameConfig(
    key="nerdle",
    display_name="Nerdle",
    pattern=re.compile(r"nerdlegame\s+([\d,]+)\s+([X\d])/6"),
    grid_emojis=frozenset({"⬛", "🟪", "🟩"}),
    grid_width=8,
    epoch=_epoch(date(2026, 4, 5), 1537),
)

ALL_GAMES: list[GameConfig] = [WORDLE, ROWORDLE, NERDLE]
GAMES_BY_KEY: dict[str, GameConfig] = {g.key: g for g in ALL_GAMES}
