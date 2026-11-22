"""Crossword numbering and layout metrics."""
from __future__ import annotations

from typing import Optional

from .types import PlacedEntry


def assign_numbers(entries: list[PlacedEntry]) -> dict[tuple[int, int], int]:
    """Number start cells in row-major order; Across and Down starting in one cell share a number."""
    starts = sorted({(e.row, e.col) for e in entries})
    numbers = {pos: i + 1 for i, pos in enumerate(starts)}
    for e in entries:
        e.number = numbers[(e.row, e.col)]
    return numbers


def symmetry_ratio(cells: list[list[Optional[str]]]) -> float:
    """Share of letter cells whose 180-degree rotation is also a letter cell (1.0 = symmetric)."""
    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    total = hits = 0
    for r in range(rows):
        for c in range(cols):
            if cells[r][c]:
                total += 1
                if cells[rows - 1 - r][cols - 1 - c]:
                    hits += 1
    return hits / total if total else 1.0
