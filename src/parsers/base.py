from games import GameConfig


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
        # Each row must have exactly grid_width cells (skip check if grid_width is 0)
        if config.grid_width and any(
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
