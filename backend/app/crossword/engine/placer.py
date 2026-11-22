"""Heuristic placement with bounded backtracking.

One *attempt* places a starting word, then repeatedly picks the most constrained
remaining word (fewest legal placements), tries its best-scoring placements, and
backtracks when stuck. The node budget and a deadline bound the work, and the
best partial layout seen is always kept so nothing is lost on failure.
"""
from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .grid import Grid
from .types import ACROSS, DOWN, EngineSettings, WordInput

WINDOW = 10      # how many placeable words are compared when choosing the next one
SCAN_CAP = 80    # max remaining words inspected per node


@dataclass
class AttemptResult:
    entries: list = field(default_factory=list)   # (answer, row, col, dir, ref)
    complete: bool = False
    nodes: int = 0
    area: int = 10 ** 9


def make_order(words: list[WordInput], strategy: str, attempt: int, rng: random.Random) -> list[WordInput]:
    if strategy == "auto":
        strategy = ("longest", "crossable", "random")[attempt % 3]
    if strategy == "longest":
        ordered = sorted(words, key=lambda w: (-len(w.answer), w.answer))
        if attempt:  # vary the starting word between attempts
            k = min(attempt, min(5, len(ordered)) - 1)
            ordered[0], ordered[k] = ordered[k], ordered[0]
        return ordered
    if strategy == "crossable":
        counts = [Counter(w.answer) for w in words]

        def share(i: int) -> int:
            return sum(sum((counts[i] & counts[j]).values()) for j in range(len(words)) if j != i)

        scored = sorted(range(len(words)), key=lambda i: (-(share(i) + 2 * len(words[i].answer)), words[i].answer))
        ordered = [words[i] for i in scored]
        if attempt:
            k = min(attempt, min(5, len(ordered)) - 1)
            ordered[0], ordered[k] = ordered[k], ordered[0]
        return ordered
    shuffled = list(words)
    rng.shuffle(shuffled)
    return shuffled


def _score(grid: Grid, answer: str, cand, rng: random.Random, sym_center) -> float:
    r, c, d, crossings = cand
    a, b, x, y = grid.bbox_after(len(answer), r, c, d)
    rows, cols = b - a + 1, y - x + 1
    s = 12.0 * crossings - (rows * cols - grid.area()) - 0.5 * abs(rows - cols)
    if sym_center is not None:
        dr, dc = (0, 1) if d == ACROSS else (1, 0)
        cr, cc = sym_center
        for k in range(len(answer)):
            pr, pc = r + dr * k, c + dc * k
            if (pr, pc) not in grid.cells and (round(2 * cr - pr), round(2 * cc - pc)) in grid.cells:
                s += 2.0
    return s + rng.random() * 0.5


def run_attempt(
    order: list[WordInput],
    max_rows: int,
    max_cols: int,
    settings: EngineSettings,
    rng: random.Random,
    deadline: float,
) -> AttemptResult:
    grid = Grid(max_rows, max_cols)
    best = AttemptResult()
    first = order[0]
    direction = ACROSS if len(first.answer) <= max_cols else DOWN
    if grid.check(first.answer, 0, 0, direction) < 0:
        return best  # first word cannot fit at all
    grid.place(first.answer, 0, 0, direction, first.ref)
    sym_center = None
    if settings.symmetry == "preferred":
        n = len(first.answer)
        sym_center = (0.0, (n - 1) / 2) if direction == ACROSS else ((n - 1) / 2, 0.0)

    nodes = 0

    def record():
        count = len(grid.entries)
        if count > len(best.entries) or (count == len(best.entries) and grid.area() < best.area):
            best.entries = list(grid.entries)
            best.area = grid.area()

    def out_of_budget() -> bool:
        return nodes >= settings.max_nodes_per_attempt or time.monotonic() > deadline

    def dfs(remaining: list[WordInput]) -> bool:
        nonlocal nodes
        record()
        if not remaining:
            return True
        if out_of_budget():
            return False
        chosen, found = None, 0
        for w in remaining[:SCAN_CAP]:
            cands = grid.candidates(w.answer)
            if not cands:
                continue
            if chosen is None or len(cands) < len(chosen[1]):
                chosen = (w, cands)
            found += 1
            if found >= WINDOW:
                break
        if chosen is None:
            return False
        word, cands = chosen
        ranked = sorted(cands, key=lambda cd: -_score(grid, word.answer, cd, rng, sym_center))
        rest = [x for x in remaining if x is not word]
        for cand in ranked[: settings.branch_factor]:
            nodes += 1
            rec = grid.place(word.answer, cand[0], cand[1], cand[2], word.ref)
            if dfs(rest):
                return True
            grid.undo(rec)
            if out_of_budget():
                return False
        return False

    best.complete = dfs(order[1:])
    best.nodes = nodes
    return best
