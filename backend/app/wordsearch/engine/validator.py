"""Independent post-generation check. Does not reuse placement code."""
from __future__ import annotations

from .directions import DIRECTIONS


def validate_puzzle(puzzle, required_words: list[str], config=None) -> list[str]:
    """Return a list of problems; an empty list means the puzzle is valid."""
    problems: list[str] = []
    g = puzzle.grid

    if len(g) != puzzle.rows or any(len(row) != puzzle.cols for row in g):
        problems.append("grid dimensions do not match rows/cols")
        return problems
    for r, row in enumerate(g):
        for c, ch in enumerate(row):
            if not isinstance(ch, str) or len(ch) != 1:
                problems.append(f"cell ({r},{c}) is empty or invalid: {ch!r}")
    if problems:
        return problems

    placed = [p.original for p in puzzle.placements]
    for w in required_words:
        if placed.count(w) != 1:
            problems.append(f"required word {w!r} placed {placed.count(w)} times")
    for w in set(placed) - set(required_words):
        problems.append(f"unexpected placement {w!r}")

    for p in puzzle.placements:
        if p.direction not in DIRECTIONS:
            problems.append(f"{p.original}: unknown direction {p.direction}")
            continue
        if puzzle.directions and p.direction not in puzzle.directions:
            problems.append(f"{p.original}: direction {p.direction} not enabled")
        dr, dc = DIRECTIONS[p.direction]
        n = len(p.grid_word)
        end_r, end_c = p.start_row + (n - 1) * dr, p.start_col + (n - 1) * dc
        if (end_r, end_c) != (p.end_row, p.end_col):
            problems.append(f"{p.original}: end coordinates inconsistent")
        for i in range(n):
            r, c = p.start_row + i * dr, p.start_col + i * dc
            if not (0 <= r < puzzle.rows and 0 <= c < puzzle.cols):
                problems.append(f"{p.original}: leaves the grid at ({r},{c})")
                break
            if g[r][c] != p.grid_word[i]:
                problems.append(
                    f"{p.original}: grid has {g[r][c]!r} at ({r},{c}), expected {p.grid_word[i]!r}")
                break
    return problems
