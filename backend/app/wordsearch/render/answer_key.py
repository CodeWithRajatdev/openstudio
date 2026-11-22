"""Answer-key data derived ONLY from engine placement metadata."""
from __future__ import annotations

from dataclasses import dataclass

from app.wordsearch.engine.models import Puzzle

DIRECTION_LABELS = {
    "E": "left to right", "W": "right to left",
    "S": "top to bottom", "N": "bottom to top",
    "SE": "diagonal down-right", "NW": "diagonal up-left",
    "SW": "diagonal down-left", "NE": "diagonal up-right",
}


@dataclass(frozen=True)
class AnswerKeyEntry:
    puzzle_id: str
    original: str
    grid_word: str
    start: tuple[int, int]      # 1-based (row, col) for humans
    end: tuple[int, int]
    direction: str
    direction_label: str
    cells: tuple[tuple[int, int], ...]   # 0-based (row, col)

    def describe(self) -> str:
        return (f"{self.original}: R{self.start[0]}C{self.start[1]} -> "
                f"R{self.end[0]}C{self.end[1]} ({self.direction_label})")


def build_answer_key(puzzle: Puzzle) -> list[AnswerKeyEntry]:
    return [
        AnswerKeyEntry(
            puzzle_id=p.puzzle_id, original=p.original, grid_word=p.grid_word,
            start=(p.start_row + 1, p.start_col + 1),
            end=(p.end_row + 1, p.end_col + 1),
            direction=p.direction, direction_label=DIRECTION_LABELS[p.direction],
            cells=tuple(p.cells()),
        )
        for p in puzzle.placements
    ]
