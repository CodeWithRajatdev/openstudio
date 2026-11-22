"""Orchestrator: sizing, multiple attempts, polish, compaction, numbering, validation."""
from __future__ import annotations

import math
import random
import sys
import time
from typing import Optional

from .numbering import assign_numbers, symmetry_ratio
from .placer import AttemptResult, make_order, run_attempt
from .types import (
    CrosswordResult,
    EngineSettings,
    PlacedEntry,
    UnplacedWord,
    ValidationReport,
    WordInput,
)
from .validator import validate_grid


def _size_schedule(words: list[WordInput], s: EngineSettings) -> list[tuple[int, int]]:
    if s.rows and s.cols:
        return [(s.rows, s.cols)]
    longest = max(len(w.answer) for w in words)
    total = sum(len(w.answer) for w in words)
    size = s.start_size or max(longest, math.ceil(math.sqrt(total / 0.6)))
    size = min(size, s.max_size)
    sizes = [size]
    while size < s.max_size:
        size = min(s.max_size, size + (1 if size < 12 else max(1, round(size * 0.07))))
        sizes.append(size)
    return [(n, n) for n in sizes]


def _crossings(entries) -> int:
    seen: dict = {}
    for answer, r, c, d, _ in entries:
        dr, dc = (0, 1) if d == "A" else (1, 0)
        for k in range(len(answer)):
            seen[(r + dr * k, c + dc * k)] = seen.get((r + dr * k, c + dc * k), 0) + 1
    return sum(1 for v in seen.values() if v > 1)


def _build(raw_entries, input_words, settings, duplicates_in_input):
    """Compact the layout into a matrix and assemble a validated result."""
    min_r = min(e[1] for e in raw_entries)
    min_c = min(e[2] for e in raw_entries)
    max_r = max(e[1] + (len(e[0]) - 1 if e[3] == "D" else 0) for e in raw_entries)
    max_c = max(e[2] + (len(e[0]) - 1 if e[3] == "A" else 0) for e in raw_entries)
    rows, cols = max_r - min_r + 1, max_c - min_c + 1
    off_r = off_c = 0
    if settings.rows and settings.cols:
        off_r, off_c = (settings.rows - rows) // 2, (settings.cols - cols) // 2
        rows, cols = settings.rows, settings.cols
    entries = [
        PlacedEntry(a, r - min_r + off_r, c - min_c + off_c, d, ref)
        for a, r, c, d, ref in raw_entries
    ]
    cells = [[None] * cols for _ in range(rows)]
    for e in entries:
        for k, (r, c) in enumerate(e.cells()):
            cells[r][c] = e.answer[k]
    entries.sort(key=lambda e: (e.row, e.col, e.direction))
    assign_numbers(entries)
    return rows, cols, cells, entries


def generate_crossword(words: list[WordInput], settings: Optional[EngineSettings] = None) -> CrosswordResult:
    settings = settings or EngineSettings()
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))
    t0 = time.monotonic()
    deadline = t0 + settings.time_limit_s
    rng = random.Random(settings.seed)

    if not words:
        return CrosswordResult(0, 0, [], [], [], "empty", ValidationReport(False, ["no words supplied"]), {})

    # exact duplicates in the input are reported, never silently merged
    unique: dict[str, WordInput] = {}
    unplaced: list[UnplacedWord] = []
    for w in words:
        if w.answer in unique:
            unplaced.append(UnplacedWord(w.answer, w.ref, "duplicate of another supplied word"))
        else:
            unique[w.answer] = w
    pool = list(unique.values())

    too_short = [w for w in pool if len(w.answer) < settings.min_word_length]
    for w in too_short:
        unplaced.append(UnplacedWord(w.answer, w.ref, f"shorter than the minimum length of {settings.min_word_length}"))
    pool = [w for w in pool if w not in too_short]

    schedule = _size_schedule(pool, settings) if pool else []
    too_long = []
    if pool:
        limit = max(max(s) for s in schedule)
        too_long = [w for w in pool if len(w.answer) > limit]
        for w in too_long:
            unplaced.append(UnplacedWord(w.answer, w.ref, f"longer than the largest allowed grid dimension ({limit})"))
        pool = [w for w in pool if w not in too_long]
    if not pool:
        return CrosswordResult(0, 0, [], [], unplaced, "empty", ValidationReport(False, ["no placeable words"]), {})

    best: Optional[AttemptResult] = None
    complete: Optional[AttemptResult] = None
    complete_size = None
    attempts = nodes = 0
    for (R, C) in _size_schedule(pool, settings):
        for k in range(settings.attempts_per_size):
            if time.monotonic() > deadline:
                break
            res = run_attempt(make_order(pool, settings.strategy, attempts, rng), R, C, settings, rng, deadline)
            attempts += 1
            nodes += res.nodes
            if best is None or (len(res.entries), -res.area) > (len(best.entries), -best.area):
                best = res
            if res.complete:
                complete, complete_size = res, (R, C)
                break
        if complete or time.monotonic() > deadline:
            break

    def quality(res: AttemptResult):
        _, _, cells, _ = _build(res.entries, pool, settings, 0)
        sym = symmetry_ratio(cells)
        key = (res.area, -_crossings(res.entries))
        return ((-round(sym, 3),) + key) if settings.symmetry == "preferred" else key

    chosen = complete or best
    if complete:
        R, C = complete_size
        chosen_q = quality(complete)
        for _ in range(settings.polish_attempts):
            if time.monotonic() > deadline:
                break
            res = run_attempt(make_order(pool, settings.strategy, attempts, rng), R, C, settings, rng, deadline)
            attempts += 1
            nodes += res.nodes
            if res.complete and quality(res) < chosen_q:
                chosen, chosen_q = res, quality(res)

    rows, cols, cells, entries = _build(chosen.entries, pool, settings, 0)

    placed = {e.answer for e in entries}
    placed_letters = set("".join(placed))
    for w in pool:
        if w.answer not in placed:
            if not set(w.answer) & placed_letters:
                reason = "shares no letters with the placed words"
            else:
                reason = "every crossing position was blocked by existing words, the no-touching rule, or the grid-size limit"
            unplaced.append(UnplacedWord(w.answer, w.ref, reason))

    report = validate_grid(
        cells,
        entries,
        expected=[w.answer for w in words],
        unplaced=[u.answer for u in unplaced],
        min_len=settings.min_word_length,
    )
    if not report.valid:
        status = "invalid"
    elif unplaced:
        status = "partial"
    else:
        status = "complete"

    letters = sum(1 for row in cells for v in row if v)
    stats = {
        "rows": rows, "cols": cols,
        "words_supplied": len(words), "words_placed": len(entries), "words_unplaced": len(unplaced),
        "crossings": _crossings([(e.answer, e.row, e.col, e.direction, None) for e in entries]),
        "density": round(letters / (rows * cols), 3) if rows * cols else 0,
        "symmetry_ratio": round(symmetry_ratio(cells), 3),
        "attempts": attempts, "nodes": nodes, "seed": settings.seed, "strategy": settings.strategy,
        "elapsed_s": round(time.monotonic() - t0, 3),
        "hit_time_limit": time.monotonic() > deadline,
    }
    return CrosswordResult(rows, cols, cells, entries, unplaced, status, report, stats)
