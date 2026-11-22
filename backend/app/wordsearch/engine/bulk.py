"""Generate many chapters; one failure never aborts the rest."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Optional

from .config import PuzzleConfig
from .generator import GenerationError, generate_puzzle
from .models import Puzzle


@dataclass
class ChapterResult:
    index: int
    title: str
    words: list[str]
    puzzle: Optional[Puzzle] = None
    error: Optional[GenerationError] = None

    @property
    def ok(self) -> bool:
        return self.puzzle is not None


@dataclass
class BulkResult:
    chapters: list[ChapterResult] = field(default_factory=list)

    @property
    def succeeded(self) -> list[ChapterResult]:
        return [c for c in self.chapters if c.ok]

    @property
    def failed(self) -> list[ChapterResult]:
        return [c for c in self.chapters if not c.ok]


def generate_chapters(chapters: list[tuple[str, list[str]]], config: PuzzleConfig,
                      base_seed: int = 0,
                      progress: Optional[Callable[[int, int], None]] = None,
                      cancelled: Optional[Callable[[], bool]] = None,
                      indices: Optional[list[int]] = None,
                      seed_overrides: Optional[dict[int, int]] = None) -> BulkResult:
    """chapters: [(title, words)]. Chapter i uses seed base_seed + i (reproducible).

    `indices` gives each chapter's position in the full book (so generating a
    subset keeps the same seeds/ids); `seed_overrides` maps that position to an
    explicit seed (used when regenerating one puzzle)."""
    result = BulkResult()
    for n, (title, words) in enumerate(chapters):
        i = indices[n] if indices is not None else n
        if cancelled and cancelled():
            break
        seed = (seed_overrides or {}).get(i, base_seed + i)
        cfg = replace(config, seed=seed)
        entry = ChapterResult(index=i, title=title, words=list(words))
        try:
            entry.puzzle = generate_puzzle(words, cfg, puzzle_id=f"ch{i + 1:03d}")
        except GenerationError as e:
            entry.error = e
        result.chapters.append(entry)
        if progress:
            progress(n + 1, len(chapters))
    return result
