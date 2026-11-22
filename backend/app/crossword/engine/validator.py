"""Independent validator. It never looks at placer state: it re-derives every
word from the finished letter matrix and compares against the declared entries.
A puzzle is only reported valid if every check passes.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import Optional

from .types import ACROSS, DOWN, PlacedEntry, ValidationReport


def _runs(cells):
    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    found = set()
    for r in range(rows):
        c = 0
        while c < cols:
            if cells[r][c]:
                s = c
                while c < cols and cells[r][c]:
                    c += 1
                if c - s >= 2:
                    found.add((r, s, ACROSS, "".join(cells[r][s:c])))
            else:
                c += 1
    for c in range(cols):
        r = 0
        while r < rows:
            if cells[r][c]:
                s = r
                while r < rows and cells[r][c]:
                    r += 1
                if r - s >= 2:
                    found.add((s, c, DOWN, "".join(cells[k][c] for k in range(s, r))))
            else:
                r += 1
    return found


def validate_grid(
    cells: list[list[Optional[str]]],
    entries: list[PlacedEntry],
    expected: Optional[list[str]] = None,
    unplaced: Optional[list[str]] = None,
    min_len: int = 2,
    require_connected: bool = True,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    def record(name: str, ok: bool, msg: str = ""):
        checks[name] = ok
        if not ok:
            errors.append(msg or name)

    rows = len(cells)
    cols = len(cells[0]) if rows else 0
    record("rectangular", all(len(r) == cols for r in cells), "grid rows have different lengths")
    record(
        "cell_values",
        all(v is None or (isinstance(v, str) and len(v) == 1 and "A" <= v <= "Z") for row in cells for v in row),
        "cells must be empty or a single A-Z letter",
    )
    if not checks["rectangular"] or not checks["cell_values"]:
        return ValidationReport(False, errors, warnings, checks)

    # entries inside the grid and consistent with the letters
    bounds_ok = letters_ok = True
    for e in entries:
        for k, (r, c) in enumerate(e.cells()):
            if not (0 <= r < rows and 0 <= c < cols):
                bounds_ok = False
            elif cells[r][c] != e.answer[k]:
                letters_ok = False
    record("entries_in_bounds", bounds_ok, "an entry lies outside the grid")
    record("entry_letters_match", letters_ok, "an entry's letters do not match the grid (invalid overlap)")
    record("min_length", all(len(e.answer) >= min_len for e in entries), f"an entry is shorter than {min_len}")
    record("no_duplicate_answers", len({e.answer for e in entries}) == len(entries), "the same answer appears twice")
    if not (bounds_ok and letters_ok):
        return ValidationReport(False, errors, warnings, checks)

    # no accidental words / no missing entries
    declared = {(e.row, e.col, e.direction, e.answer) for e in entries}
    actual = _runs(cells)
    extra = sorted(actual - declared)
    missing = sorted(declared - actual)
    record("no_accidental_words", not extra, f"unintended letter runs formed words not in the entry list: {extra[:5]}")
    record("entries_are_maximal_runs", not missing, f"entries that are not complete runs in the grid: {missing[:5]}")

    covered = {p for e in entries for p in e.cells()}
    letter_cells = {(r, c) for r in range(rows) for c in range(cols) if cells[r][c]}
    record("no_orphan_letters", letter_cells <= covered, "grid contains letters that belong to no entry")

    if require_connected and letter_cells:
        start = next(iter(letter_cells))
        seen, queue = {start}, deque([start])
        while queue:
            r, c = queue.popleft()
            for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if n in letter_cells and n not in seen:
                    seen.add(n)
                    queue.append(n)
        record("connected", seen == letter_cells, "the grid is not one connected structure")
    else:
        checks["connected"] = True

    # numbering must match a row-major scan of start cells
    starts = sorted({(e.row, e.col) for e in entries})
    expected_numbers = {pos: i + 1 for i, pos in enumerate(starts)}
    record(
        "numbering",
        all(e.number == expected_numbers[(e.row, e.col)] for e in entries),
        "entry numbers do not match row-major numbering",
    )

    if expected is not None:
        got = Counter(e.answer for e in entries) + Counter(unplaced or [])
        record("every_word_accounted_for", got == Counter(expected), "a supplied word is neither placed nor reported unplaced")

    return ValidationReport(not errors, errors, warnings, checks)
