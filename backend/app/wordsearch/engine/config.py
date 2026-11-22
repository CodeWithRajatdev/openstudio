from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .normalize import NormalizeRules


class SizingMode(str, Enum):
    AUTO = "auto"                   # engine picks the size
    MANUAL = "manual"               # exact size or fail
    MANUAL_AUTO_ADJUST = "manual_auto_adjust"  # start here, grow on failure


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class PuzzleConfig:
    sizing_mode: SizingMode = SizingMode.AUTO
    rows: int = 15                  # used by MANUAL / MANUAL_AUTO_ADJUST
    cols: int = 15
    max_rows: int = 40              # growth ceiling for AUTO / MANUAL_AUTO_ADJUST
    max_cols: int = 40
    horizontal: bool = True
    vertical: bool = True
    diagonal: bool = True
    reverse: bool = False
    # Optional explicit direction list (e.g. ["NE"]); overrides the category switches.
    directions: Optional[list[str]] = None
    seed: Optional[int] = None      # None -> a seed is generated and recorded
    attempts_per_size: int = 40
    fill_alphabet: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    normalize: NormalizeRules = field(default_factory=NormalizeRules)
    # Auto sizing starts at this cells-per-letter ratio (higher = bigger grid).
    density_factor: float = 1.8

    def validate(self) -> None:
        if self.rows < 1 or self.cols < 1:
            raise ValueError("rows and cols must be >= 1")
        if self.max_rows < self.rows or self.max_cols < self.cols:
            raise ValueError("max_rows/max_cols must be >= rows/cols")
        if self.attempts_per_size < 1:
            raise ValueError("attempts_per_size must be >= 1")
        if self.directions is not None:
            from .directions import DIRECTIONS
            unknown = [d for d in self.directions if d not in DIRECTIONS]
            if unknown:
                raise ValueError(f"unknown directions: {unknown}")
        if not self.fill_alphabet:
            raise ValueError("fill_alphabet must not be empty")


def difficulty_preset(level: Difficulty, **overrides) -> PuzzleConfig:
    """Easy/Medium/Hard presets. Every field can be overridden manually."""
    presets = {
        Difficulty.EASY: dict(horizontal=True, vertical=False, diagonal=False,
                              reverse=False, density_factor=2.4),
        Difficulty.MEDIUM: dict(horizontal=True, vertical=True, diagonal=True,
                                reverse=False, density_factor=1.9),
        Difficulty.HARD: dict(horizontal=True, vertical=True, diagonal=True,
                              reverse=True, density_factor=1.5),
    }
    params = {**presets[Difficulty(level)], **overrides}
    return PuzzleConfig(**params)
