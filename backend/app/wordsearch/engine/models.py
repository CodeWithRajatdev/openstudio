from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

ENGINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class Placement:
    """Source of truth for answer keys."""
    puzzle_id: str
    original: str          # shown in the clue list, never altered
    grid_word: str         # normalised letters as read along the path
    start_row: int
    start_col: int
    end_row: int
    end_col: int
    direction: str         # key of DIRECTIONS

    def cells(self) -> list[tuple[int, int]]:
        from .directions import DIRECTIONS
        dr, dc = DIRECTIONS[self.direction]
        return [(self.start_row + i * dr, self.start_col + i * dc)
                for i in range(len(self.grid_word))]


@dataclass
class Puzzle:
    puzzle_id: str
    rows: int
    cols: int
    grid: list[list[str]]
    placements: list[Placement]
    seed: int
    engine_version: str
    directions: list[str]
    sizing_mode: str
    requested_size: Optional[tuple[int, int]] = None
    sizes_tried: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
