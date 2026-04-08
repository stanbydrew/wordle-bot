import games
from games import GameConfig
from .base import parse_result
from .custom import CUSTOM_PARSERS


def detect_all_games(content: str) -> list[tuple[GameConfig, int, int | None, bool]]:
    """Try all game configs, return all matches found in the message."""
    results = []
    for config in games.ALL_GAMES:
        parser = CUSTOM_PARSERS.get(config.key)
        result = parser(content) if parser else parse_result(content, config)
        if result is not None:
            results.append((config, *result))
    return results
