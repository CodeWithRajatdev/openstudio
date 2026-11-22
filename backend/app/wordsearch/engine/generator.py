"""Word-search placement engine.

Pipeline: normalise -> choose size(s) -> attempt placement (backtracking CSP,
longest first, overlap-prioritised random candidates) -> weighted frequency fill
-> validate.
A Puzzle is returned only if the independent validator finds zero problems.
"""
from __future__ import annotations

import itertools
import math
import random
import uuid
from typing import Optional

from .config import PuzzleConfig, SizingMode
from .directions import DIRECTIONS, REVERSE, allowed_directions
from .models import ENGINE_VERSION, Placement, Puzzle
from .normalize import InvalidWordError, normalize_word
from .validator import validate_puzzle

# Standard English letter relative frequencies (%) so filler cells camouflage target words.
ENGLISH_LETTER_FREQUENCIES: dict[str, float] = {
    "E": 12.70,
    "T": 9.06,
    "A": 8.17,
    "O": 7.51,
    "I": 6.97,
    "N": 6.75,
    "S": 6.33,
    "H": 6.09,
    "R": 5.99,
    "D": 4.25,
    "L": 4.03,
    "C": 2.78,
    "U": 2.76,
    "M": 2.41,
    "W": 2.36,
    "F": 2.23,
    "G": 2.02,
    "Y": 1.97,
    "P": 1.93,
    "B": 1.49,
    "V": 0.98,
    "K": 0.77,
    "J": 0.15,
    "X": 0.15,
    "Q": 0.10,
    "Z": 0.07,
}

# Maximum backtracks per attempt before trying a fresh shuffle or growing the grid.
_MAX_BACKTRACKS_PER_ATTEMPT = 500

# Predefined list of inappropriate strings screened out of filled grids.
INAPPROPRIATE_WORDS: frozenset[str] = frozenset({
    "ANAL", "ANUS", "ARSE", "ASS", "BASTARD", "BITCH", "BLOWJOB", "BONER",
    "BULLSHIT", "CHINK", "CLIT", "COCK", "COON", "CRAP", "CUM", "CUNT",
    "DAMN", "DICK", "DIKE", "DILDO", "DUMBASS", "DYKE", "FAG", "FAGGOT",
    "FAGOT", "FUCK", "FUCKER", "GOOK", "HELL", "HOMO", "JACKASS", "JERK",
    "JIZZ", "KIKE", "KUNT", "MILF", "MOTHERFUCK", "MUFF", "NAZI", "NIGGA",
    "NIGGER", "PAKI", "PENIS", "PISS", "POON", "PORN", "PRICK", "PUSSY",
    "QUEEF", "QUEER", "RAPE", "SCHLONG", "SEX", "SHAG", "SHIT", "SHITE",
    "SHITHEAD", "SKANK", "SLUT", "SMUT", "SPERM", "SPIC", "TIT", "TITS",
    "TITTIES", "TURD", "TWAT", "VAGINA", "WANK", "WHORE", "WTF",
})

_MAX_REFILL_PASSES = 20


class GenerationError(Exception):
    """Raised when a puzzle cannot be generated. Never returns a partial puzzle."""

    def __init__(self, message: str, *, failed_words: list[str] | None = None,
                 sizes_tried: list[tuple[int, int]] | None = None,
                 suggestions: list[str] | None = None):
        super().__init__(message)
        self.failed_words = failed_words or []
        self.sizes_tried = sizes_tried or []
        self.suggestions = suggestions or []


def _candidates(grid, rows, cols, word, directions):
    """Every (row, col, direction) where `word` fits without conflicts."""
    n = len(word)
    if n == 0:
        return []
    first_ch = word[0]
    out = []
    for d in directions:
        dr, dc = DIRECTIONS[d]
        # Restrict start cells so the end cell is inside the grid.
        r_lo = 0 if dr >= 0 else n - 1
        r_hi = rows - 1 if dr <= 0 else rows - n
        c_lo = 0 if dc >= 0 else n - 1
        c_hi = cols - 1 if dc <= 0 else cols - n
        if r_lo > r_hi or c_lo > c_hi:
            continue
        for r in range(r_lo, r_hi + 1):
            row_r = grid[r]
            for c in range(c_lo, c_hi + 1):
                cell0 = row_r[c]
                if cell0 is not None and cell0 != first_ch:
                    continue
                rr = r
                cc = c
                ok = True
                for i in range(1, n):
                    rr += dr
                    cc += dc
                    cell = grid[rr][cc]
                    if cell is not None and cell != word[i]:
                        ok = False
                        break
                if ok:
                    out.append((r, c, d))
    return out


_REVERSE_SET: frozenset[str] = frozenset(REVERSE)


def _target_reverse_count(n_words: int, rng: random.Random) -> int:
    """Choose a target reverse-word count in the 20-30% range."""
    if n_words <= 0:
        return 0
    if n_words < 4:
        return 1 if rng.random() < 0.25 else 0
    lo = math.ceil(0.20 * n_words)
    hi = math.floor(0.30 * n_words)
    if lo <= hi:
        return rng.randint(lo, hi)
    return round(0.25 * n_words)


def _candidates_partitioned(
    grid,
    rows,
    cols,
    word,
    directions,
    rng,
    prefer_reverse: Optional[bool] = None,
):
    """Return valid (row, col, direction) candidates.

    Overlapping placements are prioritised over free placements. When
    `prefer_reverse` is set, candidates matching that polarity come first
    (with the opposite polarity kept as fallback for tight grids).
    """
    n = len(word)
    if n == 0:
        return []
    first_ch = word[0]
    pref_overlap = []
    pref_free = []
    alt_overlap = []
    alt_free = []
    for d in directions:
        dr, dc = DIRECTIONS[d]
        r_lo = 0 if dr >= 0 else n - 1
        r_hi = rows - 1 if dr <= 0 else rows - n
        c_lo = 0 if dc >= 0 else n - 1
        c_hi = cols - 1 if dc <= 0 else cols - n
        if r_lo > r_hi or c_lo > c_hi:
            continue
        is_pref = prefer_reverse is None or ((d in _REVERSE_SET) == prefer_reverse)
        for r in range(r_lo, r_hi + 1):
            row_r = grid[r]
            for c in range(c_lo, c_hi + 1):
                cell0 = row_r[c]
                if cell0 is not None and cell0 != first_ch:
                    continue
                has_overlap = cell0 is not None
                rr = r
                cc = c
                ok = True
                for i in range(1, n):
                    rr += dr
                    cc += dc
                    cell = grid[rr][cc]
                    if cell is not None:
                        if cell != word[i]:
                            ok = False
                            break
                        has_overlap = True
                if ok:
                    cand = (r, c, d)
                    if is_pref:
                        if has_overlap:
                            pref_overlap.append(cand)
                        else:
                            pref_free.append(cand)
                    else:
                        if has_overlap:
                            alt_overlap.append(cand)
                        else:
                            alt_free.append(cand)
    rng.shuffle(pref_overlap)
    rng.shuffle(pref_free)
    if prefer_reverse is None:
        return pref_overlap + pref_free
    rng.shuffle(alt_overlap)
    rng.shuffle(alt_free)
    return pref_overlap + pref_free + alt_overlap + alt_free


def _can_fit_empty_grid(word_len: int, rows: int, cols: int, directions: list[str]) -> bool:
    """Fast O(|directions|) check whether a word of `word_len` can fit on an empty grid."""
    for d in directions:
        dr, dc = DIRECTIONS[d]
        r_ok = (word_len <= rows) if dr != 0 else (rows >= 1)
        c_ok = (word_len <= cols) if dc != 0 else (cols >= 1)
        if r_ok and c_ok:
            return True
    return False


def _has_candidate(grid, rows, cols, word, directions) -> bool:
    """Fast forward-check: True as soon as at least one valid placement exists for `word`."""
    n = len(word)
    if n == 0:
        return False
    first_ch = word[0]
    for d in directions:
        dr, dc = DIRECTIONS[d]
        r_lo = 0 if dr >= 0 else n - 1
        r_hi = rows - 1 if dr <= 0 else rows - n
        c_lo = 0 if dc >= 0 else n - 1
        c_hi = cols - 1 if dc <= 0 else cols - n
        if r_lo > r_hi or c_lo > c_hi:
            continue
        for r in range(r_lo, r_hi + 1):
            row_r = grid[r]
            for c in range(c_lo, c_hi + 1):
                cell0 = row_r[c]
                if cell0 is not None and cell0 != first_ch:
                    continue
                rr = r
                cc = c
                ok = True
                for i in range(1, n):
                    rr += dr
                    cc += dc
                    cell = grid[rr][cc]
                    if cell is not None and cell != word[i]:
                        ok = False
                        break
                if ok:
                    return True
    return False


def _try_place_all(entries, rows, cols, directions, rng, puzzle_id,
                   max_backtracks: int = _MAX_BACKTRACKS_PER_ATTEMPT):
    """Backtracking CSP placement attempt. Returns (grid, placements, failed_originals)."""
    grid: list[list[Optional[str]]] = [[None] * cols for _ in range(rows)]

    # Fast domain check: any word that cannot fit on an empty grid makes this size impossible.
    impossible = [orig for orig, word in entries
                  if not _can_fit_empty_grid(len(word), rows, cols, directions)]
    if impossible:
        return grid, [], impossible

    # Most-constrained variable ordering: longest words first, random tie-breaking.
    order = sorted(entries, key=lambda e: (-len(e[1]), rng.random()))
    n_words = len(order)
    chosen: list[Optional[tuple[int, int, str]]] = [None] * n_words
    backtracks = 0
    deepest_idx = 0

    has_forward = any(d not in _REVERSE_SET for d in directions)
    has_reverse = any(d in _REVERSE_SET for d in directions)
    balance_reverse = has_forward and has_reverse
    target_rev = _target_reverse_count(n_words, rng) if balance_reverse else 0

    def backtrack(idx: int, rev_count: int) -> bool:
        nonlocal backtracks, deepest_idx
        if idx > deepest_idx:
            deepest_idx = idx
        if idx == n_words:
            return True

        prefer_reverse: Optional[bool] = None
        if balance_reverse:
            remaining = n_words - idx
            needed = target_rev - rev_count
            if needed <= 0:
                prefer_reverse = False
            elif needed >= remaining:
                prefer_reverse = True
            else:
                prefer_reverse = rng.random() < (needed / remaining)

        _, word = order[idx]
        cands = _candidates_partitioned(
            grid, rows, cols, word, directions, rng, prefer_reverse=prefer_reverse
        )
        if not cands:
            backtracks += 1
            return False

        for r, c, d in cands:
            dr, dc = DIRECTIONS[d]
            written: list[tuple[int, int]] = []
            rr = r
            cc = c
            for ch in word:
                if grid[rr][cc] is None:
                    grid[rr][cc] = ch
                    written.append((rr, cc))
                rr += dr
                cc += dc

            # Forward check: ensure every remaining unplaced word still has >= 1 valid placement.
            forward_ok = True
            for next_idx in range(idx + 1, n_words):
                if not _has_candidate(grid, rows, cols, order[next_idx][1], directions):
                    forward_ok = False
                    if next_idx > deepest_idx:
                        deepest_idx = next_idx
                    break

            if forward_ok:
                chosen[idx] = (r, c, d)
                next_rev = rev_count + (1 if d in _REVERSE_SET else 0)
                if backtrack(idx + 1, next_rev):
                    return True
                chosen[idx] = None
            else:
                backtracks += 1

            # Step back: undo only the cells written by this word placement.
            for wr, wc in written:
                grid[wr][wc] = None

            if backtracks >= max_backtracks:
                return False

        backtracks += 1
        return False

    if not backtrack(0, 0):
        failed = [order[i][0] for i in range(deepest_idx, n_words)]
        return grid, [], failed or [order[-1][0]]

    placements: list[Placement] = []
    for idx, (original, word) in enumerate(order):
        coord = chosen[idx]
        assert coord is not None
        r, c, d = coord
        dr, dc = DIRECTIONS[d]
        placements.append(Placement(
            puzzle_id=puzzle_id, original=original, grid_word=word,
            start_row=r, start_col=c,
            end_row=r + (len(word) - 1) * dr, end_col=c + (len(word) - 1) * dc,
            direction=d,
        ))
    return grid, placements, []


def _weighted_fill_distribution(alphabet: str) -> tuple[list[str], list[float]]:
    """Build population and cumulative weights for `alphabet` using English letter frequencies."""
    letters = list(alphabet)
    weights = [ENGLISH_LETTER_FREQUENCIES.get(ch.upper(), 1.0) for ch in letters]
    cum_weights = list(itertools.accumulate(weights))
    return letters, cum_weights


def _grid_line_coordinates(rows: int, cols: int) -> list[list[tuple[int, int]]]:
    """Return coordinate lists for all horizontal (E), vertical (S), and diagonal (SE, SW) lines."""
    lines: list[list[tuple[int, int]]] = []
    # Horizontal (E)
    for r in range(rows):
        lines.append([(r, c) for c in range(cols)])
    # Vertical (S)
    for c in range(cols):
        lines.append([(r, c) for r in range(rows)])
    # Diagonal (SE)
    for c in range(cols):
        lines.append([(k, c + k) for k in range(min(rows, cols - c))])
    for r in range(1, rows):
        lines.append([(r + k, k) for k in range(min(rows - r, cols))])
    # Diagonal (SW)
    for c in range(cols):
        lines.append([(k, c - k) for k in range(min(rows, c + 1))])
    for r in range(1, rows):
        lines.append([(r + k, cols - 1 - k) for k in range(min(rows - r, cols))])
    return lines


def _count_hits_capped(corpus: str, target: str, cap: int = 3) -> int:
    """Count occurrences (including overlapping) of `target` in `corpus`, stopping at `cap`."""
    hits = 0
    idx = corpus.find(target)
    while idx != -1:
        hits += 1
        if hits >= cap:
            return hits
        idx = corpus.find(target, idx + 1)
    return hits


def _validate_and_refill_grid(
    grid: list[list[str]],
    placements: list[Placement],
    rng: random.Random,
    fill_letters: list[str],
    fill_cum_weights: list[float],
    forbidden_words: frozenset[str] = INAPPROPRIATE_WORDS,
    max_passes: int = _MAX_REFILL_PASSES,
) -> int:
    """Scan the filled 2D grid horizontally, vertically, and diagonally for
    accidental duplicate clue words or inappropriate strings, and refill any
    non-placement cells involved in a match.

    Returns the total number of cells refilled.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    if rows == 0 or cols == 0:
        return 0

    locked_cells: set[tuple[int, int]] = set()
    intended_spans: dict[str, set[tuple[tuple[int, int], ...]]] = {}
    clue_words: list[str] = []
    seen_clues: set[str] = set()
    for p in placements:
        cells = tuple(p.cells())
        locked_cells.update(cells)
        spans = intended_spans.setdefault(p.grid_word, set())
        spans.add(cells)
        spans.add(cells[::-1])
        if p.grid_word not in seen_clues:
            seen_clues.add(p.grid_word)
            clue_words.append(p.grid_word)

    all_targets = list(forbidden_words) + clue_words
    if not all_targets:
        return 0
    min_len = min(len(t) for t in all_targets)
    line_coords = [coords for coords in _grid_line_coordinates(rows, cols) if len(coords) >= min_len]
    if not line_coords:
        return 0

    unique_alphabet = len(set(fill_letters)) > 1
    total_refilled = 0

    for _ in range(max_passes):
        line_strs = ["".join(grid[r][c] for r, c in coords) for coords in line_coords]
        forward_corpus = "\x00".join(line_strs)
        reverse_corpus = forward_corpus[::-1]

        suspects: list[str] = []
        for bad in forbidden_words:
            if bad in forward_corpus or bad in reverse_corpus:
                suspects.append(bad)
        for word in clue_words:
            expected_hits = 2 if word == word[::-1] else 1
            f_hits = _count_hits_capped(forward_corpus, word, expected_hits + 1)
            r_hits = _count_hits_capped(reverse_corpus, word, expected_hits + 1)
            if f_hits + r_hits > expected_hits:
                suspects.append(word)

        if not suspects:
            break

        cells_to_refill: set[tuple[int, int]] = set()
        for coords, s in zip(line_coords, line_strs):
            s_len = len(s)
            rev_s = s[::-1]
            rev_coords = coords[::-1]
            for target in suspects:
                t_len = len(target)
                if t_len > s_len:
                    continue
                allowed_spans = intended_spans.get(target)
                # Scan forward axis (E, S, SE, SW)
                idx = s.find(target)
                while idx != -1:
                    span = tuple(coords[idx : idx + t_len])
                    if not allowed_spans or span not in allowed_spans:
                        for cell in span:
                            if cell not in locked_cells:
                                cells_to_refill.add(cell)
                    idx = s.find(target, idx + 1)
                # Scan reverse axis (W, N, NW, NE)
                idx = rev_s.find(target)
                while idx != -1:
                    span = tuple(rev_coords[idx : idx + t_len])
                    if not allowed_spans or span not in allowed_spans:
                        for cell in span:
                            if cell not in locked_cells:
                                cells_to_refill.add(cell)
                    idx = rev_s.find(target, idx + 1)

        if not cells_to_refill:
            break

        for r, c in sorted(cells_to_refill):
            old_ch = grid[r][c]
            new_ch = rng.choices(fill_letters, cum_weights=fill_cum_weights, k=1)[0]
            if unique_alphabet:
                for _attempt in range(8):
                    if new_ch != old_ch:
                        break
                    new_ch = rng.choices(fill_letters, cum_weights=fill_cum_weights, k=1)[0]
            grid[r][c] = new_ch
        total_refilled += len(cells_to_refill)

    return total_refilled


def _initial_auto_size(entries, cfg: PuzzleConfig) -> tuple[int, int]:
    longest = max(len(w) for _, w in entries)
    total = sum(len(w) for _, w in entries)
    side = max(longest, math.ceil(math.sqrt(total * cfg.density_factor)))
    return side, side


def _size_schedule(entries, cfg: PuzzleConfig) -> list[tuple[int, int]]:
    if cfg.sizing_mode == SizingMode.MANUAL:
        return [(cfg.rows, cfg.cols)]
    if cfg.sizing_mode == SizingMode.AUTO:
        r, c = _initial_auto_size(entries, cfg)
    else:
        r, c = cfg.rows, cfg.cols
    sizes: list[tuple[int, int]] = []
    while r <= cfg.max_rows and c <= cfg.max_cols:
        sizes.append((r, c))
        r += 1
        c += 1
    if not sizes:  # start already beyond max
        sizes.append((min(r, cfg.max_rows), min(c, cfg.max_cols)))
    return sizes


def generate_puzzle(words: list[str], config: Optional[PuzzleConfig] = None,
                    puzzle_id: Optional[str] = None) -> Puzzle:
    cfg = config or PuzzleConfig()
    cfg.validate()
    if not words:
        raise GenerationError("No words supplied.")

    # --- normalise: reject, never drop -----------------------------------
    entries: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    bad: list[str] = []
    for original in words:
        try:
            norm = normalize_word(original, cfg.normalize)
        except InvalidWordError:
            bad.append(original)
            continue
        if norm in seen:
            raise GenerationError(
                f"Duplicate word after normalisation: {original!r} and "
                f"{seen[norm]!r} both become {norm!r}.",
                failed_words=[original],
                suggestions=["Remove or rename one of the duplicates."])
        seen[norm] = original
        entries.append((original, norm))
    if bad:
        raise GenerationError(
            f"{len(bad)} word(s) cannot be placed in a grid: {bad}",
            failed_words=bad,
            suggestions=["Edit or remove these entries, or relax the normalisation rules."])

    directions = (list(cfg.directions) if cfg.directions is not None else
                  allowed_directions(cfg.horizontal, cfg.vertical, cfg.diagonal, cfg.reverse))
    if not directions:
        raise GenerationError("No directions enabled.",
                              suggestions=["Enable horizontal, vertical or diagonal."])

    seed = cfg.seed if cfg.seed is not None else random.SystemRandom().randrange(2**32)
    pid = puzzle_id or uuid.uuid4().hex[:12]
    sizes = _size_schedule(entries, cfg)
    longest = max(len(w) for _, w in entries)
    fill_letters, fill_cum_weights = _weighted_fill_distribution(cfg.fill_alphabet)

    tried: list[tuple[int, int]] = []
    last_failed: list[str] = []
    for rows, cols in sizes:
        tried.append((rows, cols))
        impossible = [orig for orig, word in entries
                      if not _can_fit_empty_grid(len(word), rows, cols, directions)]
        if impossible:
            last_failed = impossible
            continue
        for attempt in range(cfg.attempts_per_size):
            rng = random.Random(f"{seed}:{rows}x{cols}:{attempt}")
            grid, placements, failed = _try_place_all(
                entries, rows, cols, directions, rng, pid)
            if failed:
                last_failed = failed
                continue
            # Fill empty cells using weighted English letter frequency distribution.
            for r in range(rows):
                for c in range(cols):
                    if grid[r][c] is None:
                        grid[r][c] = rng.choices(
                            fill_letters, cum_weights=fill_cum_weights, k=1
                        )[0]
            # Scan 2D grid across all 8 directions for accidental duplicate clues or
            # inappropriate words and locally refill those filler cells.
            _validate_and_refill_grid(
                grid,  # type: ignore[arg-type]
                placements,
                rng,
                fill_letters,
                fill_cum_weights,
            )
            puzzle = Puzzle(
                puzzle_id=pid, rows=rows, cols=cols, grid=grid,  # type: ignore[arg-type]
                placements=sorted(placements, key=lambda p: p.original.upper()),
                seed=seed, engine_version=ENGINE_VERSION, directions=directions,
                sizing_mode=cfg.sizing_mode.value,
                requested_size=(cfg.rows, cfg.cols) if cfg.sizing_mode != SizingMode.AUTO else None,
                sizes_tried=tried,
            )
            problems = validate_puzzle(puzzle, [o for o, _ in entries], cfg)
            if problems:  # defensive: should be unreachable
                raise GenerationError("Internal validation failed: " + "; ".join(problems))
            return puzzle

    suggestions = []
    if cfg.sizing_mode == SizingMode.MANUAL:
        suggestions.append("Increase rows/columns or switch to 'Manual + Auto-adjust'.")
        if longest > max(cfg.rows, cfg.cols):
            suggestions.append(
                f"Longest word has {longest} letters, which exceeds the grid.")
    else:
        suggestions.append("Raise the maximum grid size or the attempt limit.")
    suggestions.append("Enable more directions (vertical, diagonal, reverse) to ease placement.")
    raise GenerationError(
        f"Could not place all words. Unplaced in the last attempt: {last_failed}. "
        f"Sizes tried: {tried}.",
        failed_words=last_failed, sizes_tried=tried, suggestions=suggestions)
