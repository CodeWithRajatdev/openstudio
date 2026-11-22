"""Grid quality metrics, threshold evaluation, retry scheduling, and plain-language diagnostics."""
from __future__ import annotations

from typing import Any, Optional

RAW_CHECK_PLAIN_MESSAGES: dict[str, str] = {
    "entries_in_bounds": "One or more words extend past the grid edges.",
    "entry_letters_match": "Two crossing words do not share the same letter where they meet.",
    "no_accidental_words": "Two parallel words touch without a dark spacer cell, forming an unintended word.",
    "entries_are_maximal_runs": "A word runs directly into another letter without a boundary cell.",
    "no_orphan_letters": "There is a stray letter on the grid that is not part of any word.",
    "connected": "The crossword grid is split into disconnected islands.",
    "no_duplicate_answers": "The same answer appears more than once in the grid.",
    "numbering": "Grid clue numbers are out of row-major order.",
    "every_word_accounted_for": "A supplied word was neither placed in the grid nor listed as unplaced.",
}


def compute_grid_quality_metrics(
    grid: list[Any],
    entries: list[Any],
    unplaced: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Compute grid quality metrics outside the engine from a validated grid and entries."""
    rows = len(grid) if grid else 0
    cols = len(grid[0]) if rows > 0 else 0
    total_cells = rows * cols

    letter_cells = 0
    for row in grid or []:
        for ch in row:
            if ch is not None and ch not in ("#", ".", " ", ""):
                letter_cells += 1

    density = round(letter_cells / total_cells, 4) if total_cells > 0 else 0.0

    cell_visits: dict[tuple[int, int], int] = {}
    for entry in entries or []:
        if isinstance(entry, dict):
            answer = str(entry.get("answer") or "")
            row = int(entry.get("row") or 0)
            col = int(entry.get("col") or 0)
            direction = str(entry.get("direction") or "A")
        else:
            answer = str(getattr(entry, "answer", "") or "")
            row = int(getattr(entry, "row", 0) or 0)
            col = int(getattr(entry, "col", 0) or 0)
            direction = str(getattr(entry, "direction", "A") or "A")
        dr, dc = (0, 1) if direction == "A" else (1, 0)
        for k in range(len(answer)):
            pos = (row + dr * k, col + dc * k)
            cell_visits[pos] = cell_visits.get(pos, 0) + 1

    crossing_count = sum(1 for count in cell_visits.values() if count > 1)
    placed_count = len(entries or [])
    unplaced_count = len(unplaced or [])

    return {
        "rows": rows,
        "cols": cols,
        "total_cells": total_cells,
        "letter_cells": letter_cells,
        "density": density,
        "crossing_count": crossing_count,
        "placed_count": placed_count,
        "unplaced_count": unplaced_count,
    }


def evaluate_quality_threshold(
    metrics: dict[str, Any],
    *,
    validation_valid: bool = True,
    min_density: float = 0.15,
    min_crossings: Optional[int] = None,
) -> dict[str, Any]:
    """Check whether a grid meets minimum placement, density, and crossing thresholds."""
    placed_count = int(metrics.get("placed_count", 0))
    unplaced_count = int(metrics.get("unplaced_count", 0))
    density = float(metrics.get("density", 0.0))
    crossing_count = int(metrics.get("crossing_count", 0))

    req_crossings = min_crossings if min_crossings is not None else (1 if placed_count >= 2 else 0)
    all_words_placed = placed_count > 0 and unplaced_count == 0
    density_ok = density >= float(min_density)
    crossings_ok = crossing_count >= int(req_crossings)
    meets_threshold = bool(validation_valid and all_words_placed and density_ok and crossings_ok)

    issues: list[str] = []
    if unplaced_count > 0:
        issues.append(f"{unplaced_count} word(s) couldn't be placed")
    if not density_ok:
        issues.append(
            f"Grid density ({density:.1%}) is below the minimum threshold ({float(min_density):.1%})."
        )
    if not crossings_ok:
        issues.append(
            f"Crossing count ({crossing_count}) is below the minimum threshold ({req_crossings})."
        )

    if not validation_valid or placed_count == 0:
        status = "Invalid"
    elif meets_threshold:
        status = "Ready"
    else:
        status = "Needs attention"

    return {
        **metrics,
        "min_density": float(min_density),
        "min_crossings": int(req_crossings),
        "all_words_placed": all_words_placed,
        "density_ok": density_ok,
        "crossings_ok": crossings_ok,
        "meets_threshold": meets_threshold,
        "status": status,
        "issues": issues,
    }


def build_plain_language_diagnostics(
    *,
    validation: Optional[dict[str, Any]],
    unplaced: list[dict[str, Any]],
    quality: dict[str, Any],
    stats: Optional[dict[str, Any]] = None,
    missing_clues: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Produce plain-language diagnostic messages while keeping raw validator checks separated for Advanced view."""
    val_dict = validation or {}
    raw_checks = dict(val_dict.get("checks") or {})
    raw_errors = list(val_dict.get("errors") or [])
    is_valid = bool(val_dict.get("valid", True))
    hit_time_limit = bool((stats or {}).get("hit_time_limit"))

    messages: list[str] = []

    if unplaced:
        names = ", ".join(str(u.get("answer", "")) for u in unplaced if u.get("answer"))
        noun = "word" if len(unplaced) == 1 else "words"
        if names:
            messages.append(
                f"{len(unplaced)} {noun} couldn't be placed: {names}. Try a larger grid or a new seed."
            )
        else:
            messages.append(f"{len(unplaced)} {noun} couldn't be placed. Try a larger grid or a new seed.")

    if not quality.get("density_ok", True):
        density_pct = float(quality.get("density", 0.0)) * 100.0
        min_pct = float(quality.get("min_density", 0.0)) * 100.0
        messages.append(
            f"Grid density ({density_pct:.0f}%) is below the {min_pct:.0f}% target. "
            "Try a new seed, edit long words, or adjust the grid size."
        )

    if not quality.get("crossings_ok", True):
        messages.append(
            f"Only {quality.get('crossing_count', 0)} word crossing(s) found "
            f"(minimum {quality.get('min_crossings', 0)}). Try a new seed or add words with shared letters."
        )

    if hit_time_limit:
        messages.append(
            "Search hit the safety time limit; this layout may not be reproducible. "
            "Try reducing the word count or using a new seed."
        )

    if not is_valid:
        failed_checks = [k for k, ok in raw_checks.items() if not ok]
        for chk in failed_checks:
            plain = RAW_CHECK_PLAIN_MESSAGES.get(chk, "Grid layout failed an internal validation check.")
            if plain not in messages:
                messages.append(plain)
        if not failed_checks:
            messages.append("The puzzle grid did not pass layout validation.")

    if missing_clues:
        messages.append(
            f"Missing clues for {len(missing_clues)} placed word(s): {', '.join(missing_clues)}."
        )

    if not is_valid:
        headline = "Invalid grid layout"
    elif messages:
        headline = messages[0]
    else:
        headline = "Valid crossword grid"

    needs_attention = bool(not is_valid or not quality.get("meets_threshold", True))

    return {
        "valid": is_valid,
        "needs_attention": needs_attention,
        "status": quality.get("status", "Ready"),
        "headline": headline,
        "messages": messages,
        "hit_time_limit": hit_time_limit,
        "raw_checks": raw_checks,
        "raw_errors": raw_errors,
    }


def build_retry_schedule(
    base_seed: int = 0,
    base_strategy: str = "auto",
    max_retries: int = 3,
) -> list[tuple[int, str]]:
    """Return a deterministic list of (seed, strategy) pairs for bounded retry attempts."""
    schedule: list[tuple[int, str]] = [(int(base_seed), str(base_strategy or "auto"))]
    fallback_strategies = ["crossable", "longest", "random", "auto"]
    for step in range(1, max(0, int(max_retries)) + 1):
        strat = fallback_strategies[(step - 1) % len(fallback_strategies)]
        schedule.append((int(base_seed) + step, strat))
    return schedule
