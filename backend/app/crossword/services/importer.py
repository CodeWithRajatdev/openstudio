"""Import parsing, validation reporting, staging, and commit service."""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..engine import EngineSettings, WordInput, format_enumeration, generate_crossword, normalize_answer
from ..models import Clue, Collection, CollectionWord, ImportBatch, Word

HEADER_ALIASES: dict[str, set[str]] = {
    "word": {"word", "answer", "term", "vocabulary", "vocab"},
    "clue": {"clue", "definition", "def", "hint", "meaning"},
    "difficulty": {"difficulty", "level", "diff"},
    "group": {"group", "collection", "chapter", "puzzle", "set", "unit"},
}

DIFFICULTY_MAP: dict[str, str] = {
    "easy": "easy",
    "e": "easy",
    "1": "easy",
    "medium": "medium",
    "med": "medium",
    "m": "medium",
    "2": "medium",
    "hard": "hard",
    "h": "hard",
    "3": "hard",
}


def decode_text_bytes(raw: bytes) -> str:
    """Decode uploaded text bytes trying utf-8-sig first, then latin-1."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def normalize_difficulty(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (normalized_difficulty, warning_message)."""
    if raw is None:
        return None, None
    cleaned = str(raw).strip().lower()
    if not cleaned:
        return None, None
    if cleaned in DIFFICULTY_MAP:
        return DIFFICULTY_MAP[cleaned], None
    return None, f"unknown difficulty '{str(raw).strip()}', treated as unspecified"


def _excel_col_name(col_idx_0: int) -> str:
    """Convert 0-based column index to Excel column letters (0 -> A, 26 -> AA)."""
    idx = col_idx_0 + 1
    parts: list[str] = []
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        parts.append(chr(ord("A") + rem))
    return "".join(reversed(parts)) or "A"


def _make_cell_ref(sheet: Optional[str], row_num: int, col_idx_0: int = 0) -> str:
    if sheet:
        return f"{sheet}!{_excel_col_name(col_idx_0)}{row_num}"
    return f"line {row_num}, col {col_idx_0 + 1}"


def _detect_headers(row: list[str]) -> Optional[dict[str, int]]:
    """Return column index mapping if row looks like a header, else None."""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row):
        key = cell.strip().lower()
        for canonical, aliases in HEADER_ALIASES.items():
            if key in aliases and canonical not in mapping:
                mapping[canonical] = idx
                break
    if "word" in mapping or len(mapping) >= 2:
        return mapping
    return None


def _sniff_csv_dialect(text: str, default_delimiter: str = ",") -> csv.Dialect | type[csv.Dialect]:
    sample = "\n".join(text.splitlines()[:20])
    if not sample.strip():
        return csv.excel
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        class _FallbackDialect(csv.excel):
            delimiter = default_delimiter

        return _FallbackDialect


@dataclass
class _RawRow:
    row_num: int
    sheet: Optional[str]
    cells: list[str]
    raw_cells: list[str]
    is_empty: bool


def _parse_delimited_rows(text: str, default_delimiter: str = ",") -> list[_RawRow]:
    dialect = _sniff_csv_dialect(text, default_delimiter=default_delimiter)
    reader = csv.reader(io.StringIO(text), dialect=dialect)
    rows: list[_RawRow] = []
    for idx, raw_cells in enumerate(reader, start=1):
        raw_strs = [str(c) if c is not None else "" for c in raw_cells]
        cells = [s.strip() for s in raw_strs]
        is_empty = all(c == "" for c in cells)
        rows.append(_RawRow(row_num=idx, sheet=None, cells=cells, raw_cells=raw_strs, is_empty=is_empty))
    return rows


def _parse_txt_rows(text: str) -> list[_RawRow]:
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    # Pick the delimiter that appears on the most lines (ties: tab > | > ; > ,).
    # csv.Sniffer is unreliable when some lines (e.g. chapter titles) have no delimiter.
    best_delim: Optional[str] = None
    best_count = 0
    for delim in ("\t", "|", ";", ","):
        count = sum(1 for ln in non_empty if delim in ln)
        if count > best_count:
            best_delim, best_count = delim, count
    if best_delim is not None:
        reader = csv.reader(io.StringIO(text), delimiter=best_delim)
        delim_rows: list[_RawRow] = []
        for idx, raw_cells in enumerate(reader, start=1):
            raw_strs = [str(c) if c is not None else "" for c in raw_cells]
            cells = [s.strip() for s in raw_strs]
            is_empty = all(c == "" for c in cells)
            delim_rows.append(
                _RawRow(row_num=idx, sheet=None, cells=cells, raw_cells=raw_strs, is_empty=is_empty)
            )
        return delim_rows
    rows: list[_RawRow] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_empty = stripped == ""
        rows.append(
            _RawRow(
                row_num=idx,
                sheet=None,
                cells=[stripped] if not is_empty else [],
                raw_cells=[line] if not is_empty else [],
                is_empty=is_empty,
            )
        )
    return rows


def _parse_excel_sheets(content: bytes) -> list[tuple[str, list[_RawRow]]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheets: list[tuple[str, list[_RawRow]]] = []
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows: list[_RawRow] = []
            for idx, raw_tuple in enumerate(ws.iter_rows(values_only=True), start=1):
                raw_strs = [str(c) if c is not None else "" for c in raw_tuple]
                cells = [s.strip() for s in raw_strs]
                is_empty = all(c == "" for c in cells)
                rows.append(
                    _RawRow(row_num=idx, sheet=sheet_name, cells=cells, raw_cells=raw_strs, is_empty=is_empty)
                )
            sheets.append((sheet_name, rows))
    finally:
        wb.close()
    return sheets


def _cell(cells: list[str], idx: Optional[int]) -> str:
    if idx is None or idx < 0 or idx >= len(cells):
        return ""
    return cells[idx]


@dataclass
class _ParseContext:
    min_word_length: int
    max_word_length: int
    valid_items: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[dict[str, Any]] = field(default_factory=list)
    empty_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    skipped_headers: list[dict[str, Any]] = field(default_factory=list)
    extra_columns: list[dict[str, Any]] = field(default_factory=list)
    cross_chapter_duplicates: list[dict[str, Any]] = field(default_factory=list)
    leading_blank_row_count: int = 0
    trailing_blank_row_count: int = 0
    group_order: list[str] = field(default_factory=list)
    groups: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    group_invalid: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    group_duplicates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    group_extra_columns: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    group_skipped_headers: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    seen_in_group: dict[str, dict[str, str]] = field(default_factory=dict)
    seen_groups_by_answer: dict[str, list[str]] = field(default_factory=dict)
    chapter_titles: list[dict[str, Any]] = field(default_factory=list)
    reserved_titles: set[str] = field(default_factory=set)
    total_rows: int = 0

    def ensure_group(self, name: str) -> None:
        if name not in self.groups:
            self.groups[name] = []
            self.group_order.append(name)


_TITLE_NUMBER_PREFIX_RE = re.compile(
    r"^\s*(?:(?:chapter|puzzle|unit|part)\s*)?\d{1,3}\s*[.):\-\u2013\u2014]\s*",
    re.IGNORECASE,
)


def clean_chapter_title(raw: str) -> str:
    """Strip a leading list number ("1. ", "2) ", "Chapter 3: ") from a chapter title line.

    The raw line is always kept in the import report; if stripping would leave
    nothing, the raw text is used unchanged.
    """
    stripped = raw.strip()
    cleaned = _TITLE_NUMBER_PREFIX_RE.sub("", stripped, count=1).strip()
    return cleaned or stripped


def evaluate_chapter_status(
    valid_items: list[dict[str, Any]],
    invalid_items: list[dict[str, Any]],
    *,
    expected_words_per_chapter: Optional[int] = None,
    grid_rows: Optional[int] = None,
    grid_cols: Optional[int] = None,
    max_grid_size: int = 40,
    min_word_length: int = 3,
    run_trial_placement: bool = True,
) -> dict[str, Any]:
    """Compute per-chapter status ('Ready', 'Missing clues', 'Words won't fit', 'Invalid') and word count check."""
    found_count = len(valid_items)
    if expected_words_per_chapter is not None:
        word_count_label = f"Expected {expected_words_per_chapter}, found {found_count}"
        word_count_matches = found_count == expected_words_per_chapter
    else:
        word_count_label = f"Found {found_count}"
        word_count_matches = True

    missing_clues = [it["answer"] for it in valid_items if not (it.get("clue") or "").strip()]

    limit_dim = max(grid_rows, grid_cols) if (grid_rows and grid_cols) else max_grid_size
    unplaced_words: list[dict[str, str]] = []
    for it in valid_items:
        ans = it["answer"]
        if len(ans) > limit_dim:
            unplaced_words.append({"answer": ans, "reason": f"longer than grid dimension ({limit_dim})"})
        elif len(ans) < min_word_length:
            unplaced_words.append({"answer": ans, "reason": f"shorter than minimum length ({min_word_length})"})

    wont_fit = len(unplaced_words) > 0
    if not wont_fit and run_trial_placement and 1 <= found_count <= 45:
        trial_inputs = [WordInput(answer=it["answer"], ref=it["answer"]) for it in valid_items]
        trial_cfg = EngineSettings(
            rows=grid_rows,
            cols=grid_cols,
            max_size=max_grid_size,
            min_word_length=min_word_length,
            attempts_per_size=2,
            polish_attempts=0,
            max_nodes_per_attempt=600,
            time_limit_s=1.0,
        )
        res = generate_crossword(trial_inputs, trial_cfg)
        if res.unplaced or res.status != "complete":
            wont_fit = True
            unplaced_words = [{"answer": u.answer, "reason": u.reason} for u in res.unplaced]

    if len(invalid_items) > 0 or found_count == 0:
        status = "Invalid"
    elif wont_fit:
        status = "Words won't fit"
    elif len(missing_clues) > 0:
        status = "Missing clues"
    else:
        status = "Ready"

    return {
        "status": status,
        "expected_count": expected_words_per_chapter,
        "found_count": found_count,
        "word_count_label": word_count_label,
        "word_count_matches": word_count_matches,
        "missing_clue_count": len(missing_clues),
        "missing_clues": missing_clues,
        "unplaced_words": unplaced_words,
    }


def _process_row_stream(
    ctx: _ParseContext,
    raw_rows: list[_RawRow],
    default_group: str,
    allow_blank_group_split: bool,
    group_prefix: str = "Group",
    is_sheet_stream: bool = False,
    first_line_is_title: bool = False,
) -> None:
    if not raw_rows:
        return

    # Find first non-empty row for header detection
    first_non_empty_idx = next((i for i, r in enumerate(raw_rows) if not r.is_empty), None)
    if first_non_empty_idx is None:
        for r in raw_rows:
            ctx.total_rows += 1
            ctx.empty_rows.append(
                {
                    "row": r.row_num,
                    "sheet": r.sheet,
                    "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                    "reason": "empty row",
                }
            )
        return

    first_row = raw_rows[first_non_empty_idx]
    detected_map = _detect_headers(first_row.cells)
    header_row = first_row
    # With chapter titles on, a file may start "Title line" then "word,clue" header.
    title_then_header = False
    if detected_map is None and first_line_is_title:
        nxt_idx = first_non_empty_idx + 1
        if nxt_idx < len(raw_rows) and not raw_rows[nxt_idx].is_empty:
            nxt_map = _detect_headers(raw_rows[nxt_idx].cells)
            if nxt_map is not None:
                detected_map = nxt_map
                header_row = raw_rows[nxt_idx]
                title_then_header = True
    had_header = detected_map is not None
    initial_header_lower: Optional[list[str]] = None
    unmapped_headers: dict[int, str] = {}
    pending_header_note: Optional[dict[str, Any]] = None

    if detected_map is not None:
        header_map = detected_map
        initial_header_lower = [c.lower() for c in header_row.cells]
        mapped_indices = set(header_map.values())
        unmapped_headers = {
            idx: cell for idx, cell in enumerate(header_row.cells) if cell and idx not in mapped_indices
        }
        if title_then_header:
            # Title row is processed as data; the header row right after it is
            # skipped (and reported) by the repeated-header check below.
            data_start_idx = first_non_empty_idx
        else:
            data_start_idx = first_non_empty_idx + 1
            header_note = {
                "row": first_row.row_num,
                "sheet": first_row.sheet,
                "cell_ref": _make_cell_ref(first_row.sheet, first_row.row_num, 0),
                "raw_cells": list(first_row.raw_cells),
                "mapped_columns": dict(header_map),
                "note": f"Header row at {_make_cell_ref(first_row.sheet, first_row.row_num, 0)} skipped",
            }
            ctx.skipped_headers.append(header_note)
            pending_header_note = header_note
    else:
        header_map = {"word": 0, "clue": 1, "difficulty": 2}
        data_start_idx = first_non_empty_idx

    # Leading empty rows before header/data
    for r in raw_rows[:first_non_empty_idx]:
        ctx.total_rows += 1
        ctx.leading_blank_row_count += 1
        ctx.empty_rows.append(
            {
                "row": r.row_num,
                "sheet": r.sheet,
                "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                "reason": "empty row",
            }
        )

    last_non_empty_idx = max(i for i, r in enumerate(raw_rows) if not r.is_empty)
    ctx.trailing_blank_row_count += sum(1 for r in raw_rows[last_non_empty_idx + 1 :] if r.is_empty)

    has_group_col = "group" in header_map
    use_blank_split = False
    if allow_blank_group_split and not has_group_col:
        blocks = 0
        in_block = False
        for r in raw_rows[data_start_idx:]:
            if r.is_empty:
                in_block = False
            else:
                if not in_block:
                    blocks += 1
                    in_block = True
        use_blank_split = blocks > 1

    block_num = 1
    saw_data_in_block = False
    mapped_indices = set(header_map.values())
    word_col_idx = header_map.get("word", 0)
    clue_col_idx = header_map.get("clue")
    diff_col_idx = header_map.get("difficulty")
    group_col_idx = header_map.get("group")

    def _current_default_group() -> str:
        if block_title is not None:
            return block_title
        if use_blank_split:
            if is_sheet_stream:
                return f"{default_group} - {group_prefix} {block_num}"
            return f"{group_prefix} {block_num}"
        return default_group

    block_title: Optional[str] = None
    block_title_entry: Optional[dict[str, Any]] = None
    need_title = first_line_is_title

    for r in raw_rows[data_start_idx:]:
        ctx.total_rows += 1
        if r.is_empty:
            if first_line_is_title:
                # With titles on, every blank row ends the current chapter block.
                if saw_data_in_block or block_title is not None:
                    if block_title is not None and not saw_data_in_block and block_title_entry is not None:
                        ctx.warnings.append(
                            {
                                "type": "chapter_title_without_words",
                                "row": block_title_entry["row"],
                                "sheet": block_title_entry["sheet"],
                                "cell_ref": block_title_entry["cell_ref"],
                                "group": block_title,
                                "raw": block_title_entry["raw"],
                                "reason": (
                                    f"chapter title '{block_title}' at {block_title_entry['cell_ref']} "
                                    "has no words under it; no chapter was created"
                                ),
                            }
                        )
                    if saw_data_in_block:
                        block_num += 1
                    saw_data_in_block = False
                    block_title = None
                    block_title_entry = None
                    need_title = True
                    reason = "blank row (chapter separator)"
                else:
                    reason = "empty row"
                ctx.empty_rows.append(
                    {
                        "row": r.row_num,
                        "sheet": r.sheet,
                        "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                        "reason": reason,
                    }
                )
                continue
            if use_blank_split and saw_data_in_block:
                block_num += 1
                saw_data_in_block = False
                ctx.empty_rows.append(
                    {
                        "row": r.row_num,
                        "sheet": r.sheet,
                        "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                        "reason": "blank row (chapter separator)",
                    }
                )
            else:
                ctx.empty_rows.append(
                    {
                        "row": r.row_num,
                        "sheet": r.sheet,
                        "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                        "reason": "empty row",
                    }
                )
            continue

        # Skip repeated identical header row at the start of a new block
        if (
            had_header
            and initial_header_lower is not None
            and not saw_data_in_block
            and [c.lower() for c in r.cells] == initial_header_lower
        ):
            target_group = _current_default_group()
            header_note = {
                "row": r.row_num,
                "sheet": r.sheet,
                "cell_ref": _make_cell_ref(r.sheet, r.row_num, 0),
                "raw_cells": list(r.raw_cells),
                "mapped_columns": dict(header_map),
                "note": f"Header row at {_make_cell_ref(r.sheet, r.row_num, 0)} skipped",
            }
            ctx.skipped_headers.append(header_note)
            ctx.group_skipped_headers.setdefault(target_group, []).append(header_note)
            continue

        if need_title:
            need_title = False
            non_empty = [(ci, c) for ci, c in enumerate(r.cells) if c != ""]
            title_col, raw_title = non_empty[0]
            base_title = clean_chapter_title(raw_title)
            unique_title = base_title
            n = 2
            while unique_title in ctx.groups or unique_title in ctx.reserved_titles:
                unique_title = f"{base_title} ({n})"
                n += 1
            ctx.reserved_titles.add(unique_title)
            title_ref = _make_cell_ref(r.sheet, r.row_num, title_col)
            block_title = unique_title
            block_title_entry = {
                "row": r.row_num,
                "sheet": r.sheet,
                "cell_ref": title_ref,
                "raw": raw_title,
                "title": unique_title,
            }
            ctx.chapter_titles.append(block_title_entry)
            if unique_title != base_title:
                ctx.warnings.append(
                    {
                        "type": "duplicate_chapter_title",
                        "row": r.row_num,
                        "sheet": r.sheet,
                        "cell_ref": title_ref,
                        "group": unique_title,
                        "raw": raw_title,
                        "reason": (
                            f"chapter title '{base_title}' at {title_ref} is used more than once; "
                            f"this chapter was named '{unique_title}' so the chapters stay separate"
                        ),
                    }
                )
            if len(non_empty) > 1:
                extra_vals = [c for _, c in non_empty[1:]]
                ctx.warnings.append(
                    {
                        "type": "title_line_extra_data",
                        "row": r.row_num,
                        "sheet": r.sheet,
                        "cell_ref": title_ref,
                        "group": unique_title,
                        "raw": raw_title,
                        "value": extra_vals,
                        "reason": (
                            f"line at {title_ref} was used as the chapter title '{unique_title}' but also "
                            f"contains {', '.join(repr(v) for v in extra_vals)}; if this is a word and clue, "
                            "turn off 'First line of each chapter is its title'"
                        ),
                    }
                )
            continue

        saw_data_in_block = True
        raw_word = _cell(r.cells, word_col_idx)
        raw_word_unstripped = _cell(r.raw_cells, word_col_idx)
        raw_clue = _cell(r.cells, clue_col_idx)
        raw_clue_unstripped = _cell(r.raw_cells, clue_col_idx)
        raw_diff = _cell(r.cells, diff_col_idx)
        raw_group = _cell(r.cells, group_col_idx) if has_group_col else ""

        if has_group_col and raw_group:
            group_name = raw_group
        else:
            group_name = _current_default_group()

        ctx.ensure_group(group_name)
        if pending_header_note is not None:
            ctx.group_skipped_headers.setdefault(group_name, []).append(pending_header_note)
            pending_header_note = None
        cell_ref = _make_cell_ref(r.sheet, r.row_num, word_col_idx)

        # Report any non-empty data outside the mapped word/clue/difficulty/group columns
        row_extras: list[dict[str, Any]] = []
        for col_idx, cell_val in enumerate(r.cells):
            if col_idx not in mapped_indices and cell_val != "":
                extra_ref = _make_cell_ref(r.sheet, r.row_num, col_idx)
                col_header = unmapped_headers.get(col_idx)
                extra_entry = {
                    "row": r.row_num,
                    "col": col_idx + 1,
                    "sheet": r.sheet,
                    "cell_ref": extra_ref,
                    "group": group_name,
                    "header": col_header,
                    "value": r.raw_cells[col_idx],
                    "reason": (
                        f"data outside word/clue columns in '{col_header}' at {extra_ref}"
                        if col_header
                        else f"data outside word/clue columns at {extra_ref}"
                    ),
                }
                row_extras.append(extra_entry)
                ctx.extra_columns.append(extra_entry)
                ctx.group_extra_columns.setdefault(group_name, []).append(extra_entry)
                ctx.warnings.append(
                    {
                        "type": "extra_column_data",
                        "row": r.row_num,
                        "col": col_idx + 1,
                        "sheet": r.sheet,
                        "cell_ref": extra_ref,
                        "group": group_name,
                        "header": col_header,
                        "value": r.raw_cells[col_idx],
                        "reason": extra_entry["reason"],
                    }
                )

        answer, problem = normalize_answer(raw_word)
        if problem is None and answer is not None:
            if len(answer) < ctx.min_word_length:
                problem = f"shorter than the minimum length of {ctx.min_word_length}"
            elif len(answer) > ctx.max_word_length:
                problem = f"longer than the maximum length of {ctx.max_word_length}"

        if problem or answer is None:
            inv_entry = {
                "row": r.row_num,
                "col": word_col_idx + 1,
                "sheet": r.sheet,
                "cell_ref": cell_ref,
                "group": group_name,
                "raw": raw_word_unstripped,
                "display": raw_word,
                "reason": problem or "invalid word",
                "extra_data": row_extras,
            }
            ctx.invalid.append(inv_entry)
            ctx.group_invalid.setdefault(group_name, []).append(inv_entry)
            continue

        group_seen = ctx.seen_in_group.setdefault(group_name, {})
        if answer in group_seen:
            dup_entry = {
                "row": r.row_num,
                "col": word_col_idx + 1,
                "sheet": r.sheet,
                "cell_ref": cell_ref,
                "group": group_name,
                "raw": raw_word_unstripped,
                "display": raw_word,
                "answer": answer,
                "first_seen_as": group_seen[answer],
                "reason": "duplicate within group",
            }
            ctx.duplicates.append(dup_entry)
            ctx.group_duplicates.setdefault(group_name, []).append(dup_entry)
            continue
        group_seen[answer] = raw_word

        difficulty, diff_warn = normalize_difficulty(raw_diff)
        if diff_warn:
            ctx.warnings.append(
                {
                    "type": "unknown_difficulty",
                    "row": r.row_num,
                    "sheet": r.sheet,
                    "cell_ref": _make_cell_ref(r.sheet, r.row_num, diff_col_idx if diff_col_idx is not None else 2),
                    "group": group_name,
                    "raw": raw_diff,
                    "answer": answer,
                    "reason": diff_warn,
                }
            )

        prior_groups = ctx.seen_groups_by_answer.setdefault(answer, [])
        if prior_groups and group_name not in prior_groups:
            cross_entry = {
                "type": "cross_group_duplicate",
                "row": r.row_num,
                "sheet": r.sheet,
                "cell_ref": cell_ref,
                "group": group_name,
                "raw": raw_word_unstripped,
                "answer": answer,
                "previous_groups": list(prior_groups),
                "reason": f"'{answer}' also appears in {', '.join(prior_groups)}",
            }
            ctx.cross_chapter_duplicates.append(cross_entry)
            ctx.warnings.append(cross_entry)
        if group_name not in prior_groups:
            prior_groups.append(group_name)

        item = {
            "answer": answer,
            "display": raw_word,
            "raw": raw_word_unstripped,
            "enumeration": format_enumeration(answer, raw_word),
            "clue": raw_clue or None,
            "raw_clue": raw_clue_unstripped or None,
            "difficulty": difficulty,
            "group": group_name,
            "row": r.row_num,
            "col": word_col_idx + 1,
            "sheet": r.sheet,
            "cell_ref": cell_ref,
            "extra_data": row_extras,
        }
        ctx.valid_items.append(item)
        ctx.groups[group_name].append(item)


def detect_source_format(filename: Optional[str], fallback: str = "txt") -> str:
    if not filename:
        return fallback
    ext = Path(filename).suffix.lower()
    if ext in {".xlsx", ".xlsm"}:
        return "excel"
    if ext in {".csv", ".tsv"}:
        return "csv"
    if ext == ".txt":
        return "txt"
    return fallback


def parse_import_payload(
    *,
    content_bytes: Optional[bytes] = None,
    text: Optional[str] = None,
    filename: Optional[str] = None,
    collection_name: Optional[str] = None,
    min_word_length: int = 3,
    max_word_length: int = 30,
    expected_words_per_chapter: Optional[int] = None,
    grid_rows: Optional[int] = None,
    grid_cols: Optional[int] = None,
    max_grid_size: int = 40,
    group_prefix: str = "Group",
    run_trial_placement: bool = True,
    first_line_is_title: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Parse CSV, Excel, TXT, or pasted text and return (source_format, report, staged_data)."""
    source_format = detect_source_format(filename, fallback="paste" if text is not None else "txt")
    default_group = (
        collection_name.strip()
        if collection_name and collection_name.strip()
        else (Path(filename).stem if filename else "Imported Words")
    )

    ctx = _ParseContext(min_word_length=min_word_length, max_word_length=max_word_length)

    if source_format == "excel":
        if content_bytes is None:
            raise ValueError("Excel import requires file bytes")
        sheets = _parse_excel_sheets(content_bytes)
        for sheet_name, rows in sheets:
            sheet_default = (
                collection_name.strip()
                if (collection_name and collection_name.strip() and len(sheets) == 1)
                else sheet_name
            )
            _process_row_stream(
                ctx,
                rows,
                default_group=sheet_default,
                allow_blank_group_split=True,
                group_prefix=group_prefix,
                is_sheet_stream=True,
                first_line_is_title=first_line_is_title,
            )
    else:
        decoded = text if text is not None else decode_text_bytes(content_bytes or b"")
        if source_format == "csv":
            default_delim = "\t" if (filename and filename.lower().endswith(".tsv")) else ","
            rows = _parse_delimited_rows(decoded, default_delimiter=default_delim)
        else:
            rows = _parse_txt_rows(decoded)
        _process_row_stream(
            ctx,
            rows,
            default_group=default_group,
            allow_blank_group_split=True,
            group_prefix=group_prefix,
            is_sheet_stream=False,
            first_line_is_title=first_line_is_title,
        )

    group_summaries: list[dict[str, Any]] = []
    for ch_idx, name in enumerate(ctx.group_order, start=1):
        items = ctx.groups.get(name, [])
        inv_items = ctx.group_invalid.get(name, [])
        dup_items = ctx.group_duplicates.get(name, [])
        extra_items = ctx.group_extra_columns.get(name, [])
        hdr_notes = ctx.group_skipped_headers.get(name, [])
        eval_info = evaluate_chapter_status(
            items,
            inv_items,
            expected_words_per_chapter=expected_words_per_chapter,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            max_grid_size=max_grid_size,
            min_word_length=min_word_length,
            run_trial_placement=run_trial_placement,
        )
        group_summaries.append(
            {
                "name": name,
                "chapter_number": ch_idx,
                "status": eval_info["status"],
                "expected_count": eval_info["expected_count"],
                "valid_count": len(items),
                "found_count": eval_info["found_count"],
                "word_count_label": eval_info["word_count_label"],
                "word_count_matches": eval_info["word_count_matches"],
                "missing_clue_count": eval_info["missing_clue_count"],
                "missing_clues": eval_info["missing_clues"],
                "invalid_count": len(inv_items),
                "invalid": inv_items,
                "duplicate_count": len(dup_items),
                "duplicates": dup_items,
                "extra_column_count": len(extra_items),
                "extra_columns": extra_items,
                "skipped_headers": hdr_notes,
                "unplaced_words": eval_info["unplaced_words"],
                "words": items,
            }
        )

    report = {
        "total_rows": ctx.total_rows,
        "valid_count": len(ctx.valid_items),
        "duplicate_count": len(ctx.duplicates),
        "invalid_count": len(ctx.invalid),
        "empty_row_count": len(ctx.empty_rows),
        "leading_blank_row_count": ctx.leading_blank_row_count,
        "trailing_blank_row_count": ctx.trailing_blank_row_count,
        "warning_count": len(ctx.warnings),
        "cross_chapter_duplicate_count": len(ctx.cross_chapter_duplicates),
        "skipped_header_count": len(ctx.skipped_headers),
        "extra_column_count": len(ctx.extra_columns),
        "group_count": len(group_summaries),
        "expected_words_per_chapter": expected_words_per_chapter,
        "min_word_length": min_word_length,
        "valid": ctx.valid_items,
        "duplicates": ctx.duplicates,
        "cross_chapter_duplicates": ctx.cross_chapter_duplicates,
        "invalid": ctx.invalid,
        "empty_rows": ctx.empty_rows,
        "warnings": ctx.warnings,
        "skipped_headers": ctx.skipped_headers,
        "extra_columns": ctx.extra_columns,
        "first_line_is_title": bool(first_line_is_title),
        "chapter_titles": ctx.chapter_titles,
        "groups": group_summaries,
        "chapters": group_summaries,
    }

    staged_data = {
        "groups": [
            {
                "name": g["name"],
                "chapter_index": idx,
                "chapter_meta": {
                    "status": g["status"],
                    "expected_count": g["expected_count"],
                    "found_count": g["found_count"],
                    "word_count_label": g["word_count_label"],
                    "invalid": g["invalid"],
                    "duplicates": g["duplicates"],
                    "extra_columns": g["extra_columns"],
                    "skipped_headers": g["skipped_headers"],
                    "unplaced_words": g["unplaced_words"],
                },
                "items": [
                    {
                        "answer": it["answer"],
                        "display": it["display"],
                        "raw": it["raw"],
                        "clue": it["clue"],
                        "raw_clue": it["raw_clue"],
                        "difficulty": it["difficulty"],
                        "cell_ref": it["cell_ref"],
                        "extra_data": it["extra_data"],
                    }
                    for it in g["words"]
                ],
            }
            for idx, g in enumerate(group_summaries)
        ]
    }
    return source_format, report, staged_data


def stage_import(
    db: Session,
    *,
    content_bytes: Optional[bytes] = None,
    text: Optional[str] = None,
    filename: Optional[str] = None,
    collection_name: Optional[str] = None,
    language: str = "en",
    min_word_length: int = 3,
    max_word_length: int = 30,
    expected_words_per_chapter: Optional[int] = None,
    grid_rows: Optional[int] = None,
    grid_cols: Optional[int] = None,
    max_grid_size: int = 40,
    group_prefix: str = "Group",
    project_id: Optional[int] = None,
    run_trial_placement: bool = True,
    first_line_is_title: bool = False,
) -> ImportBatch:
    source_format, report, staged_data = parse_import_payload(
        content_bytes=content_bytes,
        text=text,
        filename=filename,
        collection_name=collection_name,
        min_word_length=min_word_length,
        max_word_length=max_word_length,
        expected_words_per_chapter=expected_words_per_chapter,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        max_grid_size=max_grid_size,
        group_prefix=group_prefix,
        run_trial_placement=run_trial_placement,
        first_line_is_title=first_line_is_title,
    )
    staged_data["language"] = language

    batch = ImportBatch(
        id=uuid.uuid4().hex,
        project_id=project_id,
        filename=filename,
        source_format=source_format,
        status="staged",
        report=report,
        staged_data=staged_data,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def commit_import(
    db: Session,
    batch: ImportBatch,
    *,
    target_collection_id: Optional[int] = None,
    project_id: Optional[int] = None,
    replace_project_chapters: bool = False,
) -> dict[str, Any]:
    if batch.status == "committed":
        raise ValueError("Import batch has already been committed")

    staged = batch.staged_data or {}
    language = staged.get("language", "en")
    groups = staged.get("groups", [])
    effective_project_id = project_id if project_id is not None else batch.project_id

    if effective_project_id is not None and replace_project_chapters:
        existing_cols = list(
            db.scalars(select(Collection).where(Collection.project_id == effective_project_id)).all()
        )
        for col in existing_cols:
            db.delete(col)
        db.flush()

    words_created = 0
    words_reused = 0
    clues_created = 0
    collections_out: list[dict[str, Any]] = []

    for g_idx, group in enumerate(groups):
        group_name = group["name"]
        items = group.get("items", [])
        chapter_meta = dict(group.get("chapter_meta") or {})
        chapter_index = int(group.get("chapter_index", g_idx))

        if target_collection_id is not None and len(groups) == 1:
            collection = db.get(Collection, target_collection_id)
            if collection is None:
                raise LookupError(f"Collection {target_collection_id} not found")
            existing_positions = [
                cw.position
                for cw in db.scalars(
                    select(CollectionWord).where(CollectionWord.collection_id == collection.id)
                ).all()
            ]
            next_pos = (max(existing_positions) + 1) if existing_positions else 0
            existing_word_ids = {
                cw.word_id
                for cw in db.scalars(
                    select(CollectionWord).where(CollectionWord.collection_id == collection.id)
                ).all()
            }
        else:
            collection = Collection(
                name=group_name,
                language=language,
                project_id=effective_project_id,
                chapter_index=chapter_index,
                chapter_meta=chapter_meta,
            )
            db.add(collection)
            db.flush()
            next_pos = 0
            existing_word_ids = set()

        added_to_collection = 0
        for item in items:
            answer = item["answer"]
            display = item["display"]
            raw_word = item.get("raw") or display
            clue_text = item.get("clue")
            raw_clue = item.get("raw_clue")
            difficulty = item.get("difficulty")
            cell_ref = item.get("cell_ref")
            extra_data = list(item.get("extra_data") or [])

            word = db.scalar(
                select(Word).where(Word.answer == answer, Word.language == language)
            )
            if word is None:
                word = Word(
                    answer=answer,
                    display=display,
                    language=language,
                    difficulty=difficulty,
                )
                db.add(word)
                db.flush()
                words_created += 1
            else:
                words_reused += 1
                if word.difficulty is None and difficulty is not None:
                    word.difficulty = difficulty
                if word.display.upper() == word.answer and any(ch in display for ch in (" ", "-", "–", "—")):
                    word.display = display

            linked_clue_id: Optional[int] = None
            if clue_text:
                existing_clue = db.scalar(
                    select(Clue).where(
                        Clue.word_id == word.id,
                        Clue.text == clue_text,
                        Clue.source == "import",
                    )
                )
                if existing_clue is None:
                    new_clue = Clue(
                        word_id=word.id,
                        text=clue_text,
                        difficulty=difficulty,
                        source="import",
                        status="approved",
                    )
                    db.add(new_clue)
                    db.flush()
                    clues_created += 1
                    linked_clue_id = new_clue.id
                else:
                    linked_clue_id = existing_clue.id

            if word.id not in existing_word_ids:
                db.add(
                    CollectionWord(
                        collection_id=collection.id,
                        word_id=word.id,
                        position=next_pos,
                        display=display,
                        raw_word=raw_word,
                        raw_clue=raw_clue,
                        cell_ref=cell_ref,
                        extra_data=extra_data,
                        clue_id=linked_clue_id,
                    )
                )
                existing_word_ids.add(word.id)
                next_pos += 1
                added_to_collection += 1

        collections_out.append(
            {
                "id": collection.id,
                "name": collection.name,
                "chapter_index": collection.chapter_index,
                "words_added": added_to_collection,
            }
        )

    batch.status = "committed"
    db.commit()

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "words_created": words_created,
        "words_reused": words_reused,
        "clues_created": clues_created,
        "collections": collections_out,
    }
