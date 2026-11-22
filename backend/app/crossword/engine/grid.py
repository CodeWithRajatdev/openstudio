"""Sparse working grid used while searching. Rules enforced here (see check()):

* a word's start/end must not touch another letter along its own axis;
* crossings must match letters and be perpendicular (no collinear overlap);
* every non-crossing cell must have empty perpendicular neighbours, so no
  accidental two-letter-or-longer runs can ever appear;
* the bounding box must stay inside the allowed rows x cols.

Connectivity is guaranteed by requiring at least one crossing for every word
after the first (see candidates()).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .types import ACROSS, DOWN

DELTA = {ACROSS: (0, 1), DOWN: (1, 0)}
BIT = {ACROSS: 1, DOWN: 2}


class Grid:
    def __init__(self, max_rows: int, max_cols: int):
        self.max_rows = max_rows
        self.max_cols = max_cols
        self.cells: dict[tuple[int, int], str] = {}
        self.mask: dict[tuple[int, int], int] = {}
        self.by_letter: dict[str, set] = defaultdict(set)  # letter -> cells used by exactly one direction
        self.entries: list[tuple[str, int, int, str, Any]] = []
        self.bbox = None  # (min_r, max_r, min_c, max_c)

    # -- geometry ---------------------------------------------------------
    def bbox_after(self, n: int, r: int, c: int, d: str):
        dr, dc = DELTA[d]
        er, ec = r + dr * (n - 1), c + dc * (n - 1)
        if self.bbox is None:
            return (r, er, c, ec)
        a, b, x, y = self.bbox
        return (min(a, r), max(b, er), min(x, c), max(y, ec))

    def dims(self):
        if self.bbox is None:
            return 0, 0
        a, b, x, y = self.bbox
        return b - a + 1, y - x + 1

    def area(self) -> int:
        rows, cols = self.dims()
        return rows * cols

    # -- rules ------------------------------------------------------------
    def check(self, answer: str, r: int, c: int, d: str) -> int:
        """Return the number of crossings, or -1 if the placement is illegal."""
        n = len(answer)
        a, b, x, y = self.bbox_after(n, r, c, d)
        if b - a + 1 > self.max_rows or y - x + 1 > self.max_cols:
            return -1
        dr, dc = DELTA[d]
        cells = self.cells
        if (r - dr, c - dc) in cells or (r + dr * n, c + dc * n) in cells:
            return -1
        pr, pc = dc, dr  # perpendicular offset
        bit = BIT[d]
        crossings = 0
        for k, ch in enumerate(answer):
            pos = (r + dr * k, c + dc * k)
            existing = cells.get(pos)
            if existing is not None:
                if existing != ch or self.mask[pos] & bit:
                    return -1
                crossings += 1
            elif (pos[0] + pr, pos[1] + pc) in cells or (pos[0] - pr, pos[1] - pc) in cells:
                return -1
        return crossings

    def candidates(self, answer: str) -> list[tuple[int, int, str, int]]:
        """All legal placements that cross at least one existing word: (row, col, dir, crossings)."""
        out, seen = [], set()
        for ch in set(answer):
            idxs = [i for i, x in enumerate(answer) if x == ch]
            for pos in sorted(self.by_letter.get(ch, ())):
                d = DOWN if self.mask[pos] == BIT[ACROSS] else ACROSS
                for i in idxs:
                    r, c = (pos[0] - i, pos[1]) if d == DOWN else (pos[0], pos[1] - i)
                    key = (r, c, d)
                    if key in seen:
                        continue
                    seen.add(key)
                    x = self.check(answer, r, c, d)
                    if x > 0:
                        out.append((r, c, d, x))
        return out

    # -- mutation ---------------------------------------------------------
    def place(self, answer: str, r: int, c: int, d: str, ref: Any = None):
        dr, dc = DELTA[d]
        bit = BIT[d]
        new, crossed = [], []
        for k, ch in enumerate(answer):
            pos = (r + dr * k, c + dc * k)
            if pos in self.cells:
                crossed.append(pos)
                self.mask[pos] |= bit
                self.by_letter[ch].discard(pos)
            else:
                self.cells[pos] = ch
                self.mask[pos] = bit
                self.by_letter[ch].add(pos)
                new.append(pos)
        prev = self.bbox
        self.bbox = self.bbox_after(len(answer), r, c, d)
        self.entries.append((answer, r, c, d, ref))
        return new, crossed, prev, bit

    def undo(self, record):
        new, crossed, prev, bit = record
        self.entries.pop()
        for pos in crossed:
            self.mask[pos] &= ~bit
            self.by_letter[self.cells[pos]].add(pos)
        for pos in new:
            ch = self.cells.pop(pos)
            del self.mask[pos]
            self.by_letter[ch].discard(pos)
        self.bbox = prev
