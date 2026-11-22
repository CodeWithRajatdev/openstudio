"""Plain data types shared by the crossword engine. No framework imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

ACROSS = "A"
DOWN = "D"


@dataclass(frozen=True)
class WordInput:
    """A normalized answer (A-Z only) plus an opaque reference (e.g. a DB id)."""
    answer: str
    ref: Any = None


@dataclass
class PlacedEntry:
    answer: str
    row: int
    col: int
    direction: str  # "A" or "D"
    ref: Any = None
    number: Optional[int] = None

    @property
    def length(self) -> int:
        return len(self.answer)

    def cells(self):
        dr, dc = (0, 1) if self.direction == ACROSS else (1, 0)
        return [(self.row + dr * k, self.col + dc * k) for k in range(len(self.answer))]


@dataclass
class UnplacedWord:
    answer: str
    ref: Any
    reason: str


@dataclass
class EngineSettings:
    rows: Optional[int] = None          # custom fixed grid size (both rows and cols required)
    cols: Optional[int] = None
    max_size: int = 40                  # upper bound for auto-sizing growth
    start_size: Optional[int] = None    # override for the first size tried
    seed: int = 0
    attempts_per_size: int = 4
    polish_attempts: int = 3            # extra attempts after the first full success
    max_nodes_per_attempt: int = 3000   # bounded backtracking budget
    branch_factor: int = 4              # candidate placements explored per node
    time_limit_s: float = 20.0          # safety limit for the whole run
    symmetry: str = "off"               # "off" | "preferred" (best effort, see HANDOVER.md)
    min_word_length: int = 3
    strategy: str = "auto"              # auto | longest | crossable | random


@dataclass
class ValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)


@dataclass
class CrosswordResult:
    rows: int
    cols: int
    cells: list[list[Optional[str]]]
    entries: list[PlacedEntry]
    unplaced: list[UnplacedWord]
    status: str                         # "complete" | "partial" | "invalid" | "empty"
    validation: ValidationReport
    stats: dict[str, Any] = field(default_factory=dict)
