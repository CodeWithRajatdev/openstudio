"""Project model service: defaults, autosave, chapter import, status, and JSON save/restore."""
from __future__ import annotations

import copy
import os
import re
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings, redact_secrets
from ..engine import EngineSettings, format_enumeration, normalize_answer
from ..models import (
    Clue,
    Collection,
    CollectionWord,
    ImportBatch,
    Job,
    Project,
    Puzzle,
    PuzzleEntry,
    Word,
    utcnow,
)
from .bulk import _run_chapter_with_retries
from .clues.service import resolve_clue_for_word
from .export.book import build_book_pdf, compute_book_page_plan
from .export.geometry import ExportEntry, ExportPuzzleData
from .export.settings import ExportSettings
from .export.verifier import PDFVerificationError
from .importer import commit_import, evaluate_chapter_status, stage_import
from .puzzles import _ensure_word, build_puzzle_export_data, generate_and_save_puzzle, serialize_puzzle
from .quality import (
    build_plain_language_diagnostics,
    compute_grid_quality_metrics,
    evaluate_quality_threshold,
)

DEFAULT_PROJECT_SETTINGS: dict[str, Any] = {
    "words_per_chapter": None,
    "min_word_length": 3,
    "max_word_length": 30,
    "enumeration_display": "formatted",
    "trim": {
        "preset": "6x9",
        "custom_width": 6.0,
        "custom_height": 9.0,
        "custom_unit": "in",
    },
    "page": {
        "guideline_mode": "kdp",
        "margin_top": 36.0,
        "margin_bottom": 36.0,
        "margin_left": 36.0,
        "margin_right": 36.0,
        "independent_margins": False,
        "gutter": 18.0,
        "start_puzzles_on_right_hand_page": False,
        "show_page_numbers": True,
    },
    "clues": {
        "mode": "hybrid",
        "difficulty": "medium",
        "verify": False,
        "age_group": "general",
        "capitalization": "sentence",
        "ending_punctuation": "keep",
        "show_length_hint": True,
        "require_all_clues_approved": False,
    },
    "grid": {
        "mode": "auto",
        "rows": 15,
        "cols": 15,
        "max_size": 40,
        "symmetry": "off",
        "strategy": "auto",
        "seed": 1,
        "min_word_length": 3,
        "min_density": 0.25,
    },
    "appearance": {
        "cell_size": 24,
        "line_width": 0.75,
        "line_unit": "pt",
        "outer_border": True,
        "border_line_width": 1.5,
        "cell_fill": "#FFFFFF",
        "empty_cell_style": "black",
        "block_color": "#000000",
        "number_size": 6.5,
        "number_position": "top_left",
        "number_font": "Open Sans",
        "number_color": "#000000",
        "font_family": "Open Sans",
        "capital_letters": True,
    },
    "clue_layout": {
        "layout_mode": "columns",
        "heading_style": "uppercase",
        "font_family": "Open Sans",
        "font_size": 9.5,
        "color": "#000000",
        "spacing": 2.0,
        "puzzle_clue_gap": 16.0,
        "sort": "number",
        "show_length_hint": True,
        "placement": "same_page",
    },
    "solution": {
        "per_page": 4,
        "title_enabled": True,
        "title_mode": "chapter_name",
        "title_template": "Puzzle {PUZZLE_NUMBER}: {CHAPTER_TITLE}",
        "title_font_family": "Open Sans",
        "title_font_size": 12.0,
        "title_color": "#000000",
        "title_alignment": "center",
        "title_gap": 8.0,
        "highlight_style": "bold",
        "copy_appearance": True,
        "font_family": "Open Sans",
        "font_size": 10.0,
        "color": "#000000",
    },
    "title": {
        "enabled": True,
        "mode": "chapter_name",
        "first_line_is_title": False,
        "template": "Chapter {PUZZLE_NUMBER}: {CHAPTER_TITLE}",
        "start_number": 1,
        "font_family": "Open Sans",
        "font_size": 16.0,
        "color": "#000000",
        "alignment": "center",
        "gap": 10.0,
    },
}


def resolve_chapter_display_title(
    chapter_name: str,
    puzzle_number: int,
    *,
    mode: str = "chapter_name",
    template: str = "",
    enabled: bool = True,
) -> str:
    """Resolve the display title for a puzzle or solution slot ('chapter_name' vs 'custom')."""
    if not enabled:
        return ""
    if mode == "custom":
        tmpl = (template or "").strip()
        if not tmpl:
            return chapter_name
        return (
            tmpl.replace("{PUZZLE_NUMBER}", str(puzzle_number))
            .replace("{CHAPTER_TITLE}", chapter_name)
            .replace("{TITLE}", chapter_name)
        )
    return chapter_name


def deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Return a new deep-merged dictionary without mutating inputs."""
    merged = copy.deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_project_settings(raw_settings: Optional[dict[str, Any]], trim_size: str = "6x9") -> dict[str, Any]:
    merged = deep_merge_dict(DEFAULT_PROJECT_SETTINGS, raw_settings or {})
    if trim_size and merged.get("trim", {}).get("preset") != trim_size:
        merged.setdefault("trim", {})["preset"] = trim_size
    wpc = merged.get("words_per_chapter")
    if wpc in (None, "", 0):
        merged["words_per_chapter"] = None
    else:
        try:
            merged["words_per_chapter"] = max(1, int(wpc))
        except (TypeError, ValueError):
            merged["words_per_chapter"] = None
    return merged


def create_project(
    db: Session,
    *,
    name: str = "Untitled Crossword Book",
    project_type: str = "crossword",
    trim_size: str = "6x9",
    current_step: int = 1,
    settings: Optional[dict[str, Any]] = None,
) -> Project:
    norm_settings = normalize_project_settings(settings, trim_size=trim_size)
    project = Project(
        name=name.strip() or "Untitled Crossword Book",
        project_type=project_type.strip() or "crossword",
        trim_size=trim_size.strip() or "6x9",
        current_step=current_step,
        settings=norm_settings,
        import_metadata={},
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.chapters)
            .selectinload(Collection.word_links)
            .selectinload(CollectionWord.word)
            .selectinload(Word.clues)
        )
    )
    if project is None:
        raise LookupError(f"Project {project_id} not found")
    return project


def list_projects(db: Session) -> list[dict[str, Any]]:
    projects = list(
        db.scalars(
            select(Project).order_by(Project.updated_at.desc(), Project.id.desc())
        ).all()
    )
    if not projects:
        return []

    chap_counts = dict(
        db.execute(
            select(Collection.project_id, func.count(Collection.id))
            .where(Collection.project_id.is_not(None))
            .group_by(Collection.project_id)
        ).all()
    )
    word_counts = dict(
        db.execute(
            select(Collection.project_id, func.count(CollectionWord.id))
            .join(CollectionWord, Collection.id == CollectionWord.collection_id)
            .where(Collection.project_id.is_not(None))
            .group_by(Collection.project_id)
        ).all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "project_type": p.project_type,
            "trim_size": p.trim_size,
            "current_step": p.current_step,
            "chapter_count": int(chap_counts.get(p.id, 0)),
            "total_words": int(word_counts.get(p.id, 0)),
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            "autosaved_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects
    ]


def update_project(
    db: Session,
    project_id: int,
    *,
    name: Optional[str] = None,
    project_type: Optional[str] = None,
    trim_size: Optional[str] = None,
    current_step: Optional[int] = None,
    settings: Optional[dict[str, Any]] = None,
    import_metadata: Optional[dict[str, Any]] = None,
) -> Project:
    project = get_project_or_404(db, project_id)
    if name is not None:
        project.name = name.strip() or project.name
    if project_type is not None:
        project.project_type = project_type.strip() or project.project_type
    if trim_size is not None:
        project.trim_size = trim_size.strip() or project.trim_size
    if current_step is not None:
        project.current_step = current_step

    merged_settings = deep_merge_dict(
        normalize_project_settings(project.settings, trim_size=project.trim_size),
        settings or {},
    )
    if trim_size is not None:
        merged_settings.setdefault("trim", {})["preset"] = project.trim_size
    elif settings and isinstance(settings.get("trim"), dict) and settings["trim"].get("preset"):
        project.trim_size = str(settings["trim"]["preset"])
    if settings and isinstance(settings.get("grid"), dict) and "min_word_length" in settings["grid"]:
        merged_settings["min_word_length"] = settings["grid"]["min_word_length"]
    elif settings and "min_word_length" in settings:
        merged_settings.setdefault("grid", {})["min_word_length"] = settings["min_word_length"]

    project.settings = merged_settings
    if import_metadata is not None:
        project.import_metadata = copy.deepcopy(import_metadata)
    project.updated_at = utcnow()
    db.commit()
    db.refresh(project)
    return get_project_or_404(db, project.id)


def delete_project(db: Session, project_id: int) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise LookupError(f"Project {project_id} not found")
    db.delete(project)
    db.commit()


def _grid_constraints(settings: dict[str, Any]) -> tuple[Optional[int], Optional[int], int, int]:
    grid_cfg = settings.get("grid") or {}
    min_len = int(grid_cfg.get("min_word_length", settings.get("min_word_length", 3)))
    max_size = int(grid_cfg.get("max_size", 40))
    if grid_cfg.get("mode") == "custom":
        return (
            int(grid_cfg.get("rows") or 15),
            int(grid_cfg.get("cols") or 15),
            max_size,
            min_len,
        )
    return None, None, max_size, min_len


def serialize_project(db: Session, project: Project, *, include_details: bool = True) -> dict[str, Any]:
    settings = normalize_project_settings(project.settings, trim_size=project.trim_size)
    clue_cfg = settings.get("clues") or {}
    clue_mode = clue_cfg.get("mode", "hybrid")
    clue_diff = clue_cfg.get("difficulty", "medium")
    expected_n = settings.get("words_per_chapter")
    enum_style = settings.get("enumeration_display", "formatted")
    grid_rows, grid_cols, max_grid_size, min_len = _grid_constraints(settings)

    chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
    chap_ids = [c.id for c in chapters]
    latest_puzzle_by_col: dict[int, Puzzle] = {}
    if chap_ids:
        puzzles = list(
            db.scalars(
                select(Puzzle)
                .where(Puzzle.collection_id.in_(chap_ids))
                .options(selectinload(Puzzle.entries))
                .order_by(Puzzle.id.asc())
            ).all()
        )
        for p in puzzles:
            if p.collection_id is not None:
                latest_puzzle_by_col[p.collection_id] = p

    grid_cfg = settings.get("grid") or {}
    default_min_density = float(grid_cfg.get("min_density", 0.15))
    chapters_out: list[dict[str, Any]] = []
    total_words = 0

    for idx, ch in enumerate(chapters, start=1):
        meta = dict(ch.chapter_meta or {})
        grid_override = dict(meta.get("grid_override") or {})
        ch_rows = (
            int(grid_override["rows"])
            if grid_override.get("mode") == "custom" and grid_override.get("rows")
            else grid_rows
        )
        ch_cols = (
            int(grid_override["cols"])
            if grid_override.get("mode") == "custom" and grid_override.get("cols")
            else grid_cols
        )
        ch_max_size = int(grid_override.get("max_size") or max_grid_size)
        invalid_items = list(meta.get("invalid") or [])
        valid_items: list[dict[str, Any]] = []
        words_out: list[dict[str, Any]] = []
        unapproved_clues: list[str] = []

        for link in ch.word_links:
            w = link.word
            disp = link.display or w.display
            active_clue = resolve_clue_for_word(
                w.clues,
                mode=clue_mode,
                difficulty=clue_diff,
                preferred_clue_id=link.clue_id,
            )
            clue_text = active_clue.text if active_clue else None
            if active_clue is not None and active_clue.status != "approved":
                unapproved_clues.append(w.answer)
            valid_items.append({"answer": w.answer, "clue": clue_text})
            if include_details:
                words_out.append(
                    {
                        "word_id": w.id,
                        "position": link.position,
                        "answer": w.answer,
                        "display": disp,
                        "raw_word": link.raw_word or disp,
                        "raw_clue": link.raw_clue,
                        "cell_ref": link.cell_ref,
                        "extra_data": list(link.extra_data or []),
                        "enumeration": format_enumeration(w.answer, disp, style=enum_style),
                        "difficulty": w.difficulty,
                        "active_clue": (
                            {
                                "id": active_clue.id,
                                "text": active_clue.text,
                                "difficulty": active_clue.difficulty,
                                "source": active_clue.source,
                                "status": active_clue.status,
                            }
                            if active_clue is not None
                            else None
                        ),
                        "clues": [
                            {
                                "id": c.id,
                                "text": c.text,
                                "difficulty": c.difficulty,
                                "source": c.source,
                                "status": c.status,
                            }
                            for c in sorted(w.clues, key=lambda x: x.id, reverse=True)
                        ],
                    }
                )

        total_words += len(valid_items)
        eval_info = evaluate_chapter_status(
            valid_items,
            invalid_items,
            expected_words_per_chapter=expected_n,
            grid_rows=ch_rows,
            grid_cols=ch_cols,
            max_grid_size=ch_max_size,
            min_word_length=min_len,
            run_trial_placement=False,
        )

        # Re-evaluate placement / quality against latest generated puzzle if present
        stored_unplaced = list(meta.get("unplaced_words") or [])
        latest_puzzle = latest_puzzle_by_col.get(ch.id)
        chapter_quality: Optional[dict[str, Any]] = meta.get("quality")
        chapter_diagnostics: Optional[dict[str, Any]] = None
        win_seed = meta.get("winning_seed")
        win_strategy = meta.get("winning_strategy")
        hit_tl = bool(meta.get("hit_time_limit", False))

        if latest_puzzle is not None:
            eval_info["unplaced_words"] = list(latest_puzzle.unplaced or [])
            puz_settings = latest_puzzle.settings or {}
            puz_q = puz_settings.get("quality") or {}
            eff_min_density = float(puz_q.get("min_density", default_min_density))
            metrics = compute_grid_quality_metrics(
                latest_puzzle.grid or [],
                latest_puzzle.entries,
                latest_puzzle.unplaced or [],
            )
            chapter_quality = evaluate_quality_threshold(
                metrics,
                validation_valid=bool((latest_puzzle.validation or {}).get("valid", True)),
                min_density=eff_min_density,
                min_crossings=puz_q.get("min_crossings"),
            )
            chapter_diagnostics = build_plain_language_diagnostics(
                validation=latest_puzzle.validation,
                unplaced=latest_puzzle.unplaced or [],
                quality=chapter_quality,
                stats=latest_puzzle.stats,
                missing_clues=eval_info["missing_clues"],
            )
            win_seed = puz_settings.get("winning_seed", (puz_settings.get("engine") or {}).get("seed"))
            win_strategy = puz_settings.get(
                "winning_strategy", (puz_settings.get("engine") or {}).get("strategy")
            )
            hit_tl = bool((latest_puzzle.stats or {}).get("hit_time_limit"))
            if eval_info["status"] != "Invalid":
                if not chapter_quality["meets_threshold"]:
                    eval_info["status"] = "Needs attention"
                elif eval_info["missing_clue_count"] > 0:
                    eval_info["status"] = "Missing clues"
                else:
                    eval_info["status"] = "Ready"
        elif stored_unplaced and eval_info["status"] != "Invalid":
            eval_info = evaluate_chapter_status(
                valid_items,
                invalid_items,
                expected_words_per_chapter=expected_n,
                grid_rows=ch_rows,
                grid_cols=ch_cols,
                max_grid_size=ch_max_size,
                min_word_length=min_len,
                run_trial_placement=True,
            )

        chapters_out.append(
            {
                "id": ch.id,
                "name": ch.name,
                "chapter_number": idx,
                "chapter_index": ch.chapter_index,
                "status": eval_info["status"],
                "expected_count": eval_info["expected_count"],
                "found_count": eval_info["found_count"],
                "word_count": eval_info["found_count"],
                "word_count_label": eval_info["word_count_label"],
                "word_count_matches": eval_info["word_count_matches"],
                "clue_status": (
                    "complete"
                    if (eval_info["found_count"] > 0 and eval_info["missing_clue_count"] == 0)
                    else "incomplete"
                ),
                "missing_clue_count": eval_info["missing_clue_count"],
                "missing_clues": eval_info["missing_clues"],
                "unapproved_clues": unapproved_clues,
                "invalid_count": len(invalid_items),
                "invalid": invalid_items,
                "duplicates": list(meta.get("duplicates") or []),
                "extra_columns": list(meta.get("extra_columns") or []),
                "skipped_headers": list(meta.get("skipped_headers") or []),
                "unplaced_words": eval_info["unplaced_words"],
                "puzzle_id": latest_puzzle.id if latest_puzzle is not None else None,
                "quality": chapter_quality,
                "winning_seed": win_seed,
                "winning_strategy": win_strategy,
                "hit_time_limit": hit_tl,
                "diagnostics": chapter_diagnostics,
                "plain_errors": chapter_diagnostics["messages"] if chapter_diagnostics else [],
                "words": words_out,
            }
        )

    require_all_approved = bool((settings.get("clues") or {}).get("require_all_clues_approved", False))
    blocking_issues, warnings = compute_project_blocking_issues(
        chapters_out,
        require_all_clues_approved=require_all_approved,
    )
    page_plan = compute_project_page_plan(
        db,
        project,
        settings=settings,
        latest_puzzle_by_col=latest_puzzle_by_col,
    )

    return {
        "id": project.id,
        "name": project.name,
        "project_type": project.project_type,
        "trim_size": project.trim_size,
        "current_step": project.current_step,
        "settings": settings,
        "import_metadata": project.import_metadata or {},
        "chapter_count": len(chapters_out),
        "total_words": total_words,
        "chapters": chapters_out,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "can_generate_and_download": len(blocking_issues) == 0,
        "page_plan": page_plan,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "autosaved_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def compute_project_blocking_issues(
    chapters_out: list[dict[str, Any]],
    *,
    require_all_clues_approved: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build plain-language blocking issues and non-blocking warnings for book export."""
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not chapters_out:
        issues.append(
            {
                "type": "no_chapters",
                "chapter_id": None,
                "chapter_number": None,
                "chapter_name": None,
                "words": [],
                "message": "No chapters imported yet. Import a word list before generating your book.",
            }
        )
        return issues, warnings

    for ch in chapters_out:
        missing = list(ch.get("missing_clues") or [])
        if missing:
            issues.append(
                {
                    "type": "missing_clues",
                    "chapter_id": ch["id"],
                    "chapter_number": ch["chapter_number"],
                    "chapter_name": ch["name"],
                    "words": missing,
                    "message": f"{ch['name']} is missing clues for: {', '.join(missing)}.",
                }
            )
        unapproved = list(ch.get("unapproved_clues") or [])
        if unapproved:
            entry = {
                "type": "unapproved_clues",
                "chapter_id": ch["id"],
                "chapter_number": ch["chapter_number"],
                "chapter_name": ch["name"],
                "words": unapproved,
                "message": f"{ch['name']} has clues awaiting review: {', '.join(unapproved)}.",
            }
            warnings.append(entry)
            if require_all_clues_approved:
                issues.append(entry)
        inv = list(ch.get("invalid") or [])
        if inv or ch.get("found_count", 0) == 0:
            inv_words = [str(i.get("raw") or i.get("display") or "empty") for i in inv]
            detail = ", ".join(inv_words) if inv_words else "no valid words"
            issues.append(
                {
                    "type": "invalid_words",
                    "chapter_id": ch["id"],
                    "chapter_number": ch["chapter_number"],
                    "chapter_name": ch["name"],
                    "words": inv_words,
                    "message": f"{ch['name']} has invalid words: {detail}.",
                }
            )
        unplaced = list(ch.get("unplaced_words") or [])
        if unplaced or ch.get("status") in ("Words won't fit", "Needs attention"):
            unp_words = [str(u.get("answer", "")) for u in unplaced if u.get("answer")]
            detail = (
                f"unplaced words: {', '.join(unp_words)}"
                if unp_words
                else "grid quality below threshold"
            )
            issues.append(
                {
                    "type": "needs_attention",
                    "chapter_id": ch["id"],
                    "chapter_number": ch["chapter_number"],
                    "chapter_name": ch["name"],
                    "words": unp_words,
                    "message": f"{ch['name']} needs attention ({detail}).",
                }
            )
    return issues, warnings


def _project_export_settings(project: Project, settings: dict[str, Any]) -> ExportSettings:
    trim = settings.get("trim") or {}
    page_cfg = settings.get("page") or {}
    clue_cfg = settings.get("clues") or {}
    app_cfg = settings.get("appearance") or {}
    cl_cfg = settings.get("clue_layout") or {}
    title_cfg = settings.get("title") or {}
    sol_cfg = settings.get("solution") or {}
    copy_app = bool(sol_cfg.get("copy_appearance", True))
    base_font = str(app_cfg.get("font_family") or "Open Sans")

    return ExportSettings(
        page_size=project.trim_size or str(trim.get("preset") or "6x9"),
        custom_width=trim.get("custom_width"),
        custom_height=trim.get("custom_height"),
        custom_unit=str(trim.get("custom_unit") or "in"),
        margin_top=float(page_cfg.get("margin_top", 36.0)),
        margin_bottom=float(page_cfg.get("margin_bottom", 36.0)),
        margin_left=float(page_cfg.get("margin_left", 36.0)),
        margin_right=float(page_cfg.get("margin_right", 36.0)),
        gutter=float(page_cfg.get("gutter", 18.0)),
        font_family=base_font,
        title_font_family=str(title_cfg.get("font_family") or base_font),
        title_font_size=float(title_cfg.get("font_size", 16.0)),
        title_color=str(title_cfg.get("color") or "#000000"),
        title_alignment=str(title_cfg.get("alignment") or "center"),
        title_gap=float(title_cfg.get("gap", 10.0)),
        solution_title_font_family=str(sol_cfg.get("title_font_family") or title_cfg.get("font_family") or base_font),
        solution_title_font_size=float(sol_cfg.get("title_font_size", 12.0)),
        solution_title_color=str(sol_cfg.get("title_color") or title_cfg.get("color") or "#000000"),
        solution_title_alignment=str(sol_cfg.get("title_alignment") or "center"),
        solution_title_gap=float(sol_cfg.get("title_gap", 8.0)),
        clue_font_family=str(cl_cfg.get("font_family") or base_font),
        clue_font_size=float(cl_cfg.get("font_size", 9.5)),
        clue_color=str(cl_cfg.get("color") or "#000000"),
        clue_spacing=float(cl_cfg.get("spacing", 2.0)),
        puzzle_clue_gap=float(cl_cfg.get("puzzle_clue_gap", 16.0)),
        clue_layout_mode=str(cl_cfg.get("layout_mode") or "columns"),
        clue_heading_style=str(cl_cfg.get("heading_style") or "uppercase"),
        clue_sort=str(cl_cfg.get("sort") or "number"),
        number_font_family=str(app_cfg.get("number_font") or base_font),
        number_font_size=float(app_cfg.get("number_size", 6.5)),
        number_color=str(app_cfg.get("number_color") or "#000000"),
        number_position=str(app_cfg.get("number_position") or "top_left"),
        capital_letters=bool(app_cfg.get("capital_letters", True)),
        solution_font_family=base_font if copy_app else str(sol_cfg.get("font_family") or base_font),
        solution_color="#000000" if copy_app else str(sol_cfg.get("color") or "#000000"),
        solution_highlight_style=str(sol_cfg.get("highlight_style") or "bold"),
        grid_line_width=float(app_cfg.get("line_width", 0.75)),
        border_line_width=float(app_cfg.get("border_line_width", 1.5))
        if app_cfg.get("outer_border", True)
        else 0.0,
        block_color=str(app_cfg.get("block_color") or "#000000"),
        cell_bg_color=str(app_cfg.get("cell_fill") or "#FFFFFF"),
        show_clue_lengths=bool(clue_cfg.get("show_length_hint", True)),
        enumeration_display=str(settings.get("enumeration_display") or "formatted"),
        clue_capitalization=str(clue_cfg.get("capitalization") or "sentence"),
        clue_ending_punctuation=str(clue_cfg.get("ending_punctuation") or "keep"),
        black_empty_cells=(str(app_cfg.get("empty_cell_style") or "black") == "black"),
    )


def _chapter_export_data_for_plan(
    db: Session,
    ch: Collection,
    latest_puzzle: Optional[Puzzle],
    *,
    clue_mode: str,
    clue_diff: str,
) -> ExportPuzzleData:
    if latest_puzzle is not None:
        return build_puzzle_export_data(db, latest_puzzle, force=True)

    entries: list[ExportEntry] = []
    for idx, link in enumerate(ch.word_links, start=1):
        w = link.word
        disp = link.display or w.display
        active = resolve_clue_for_word(
            w.clues, mode=clue_mode, difficulty=clue_diff, preferred_clue_id=link.clue_id
        )
        entries.append(
            ExportEntry(
                number=idx,
                direction="A" if idx % 2 else "D",
                row=0,
                col=0,
                answer=w.answer,
                clue=active.text if active else "[Missing clue]",
                display=disp,
            )
        )
    return ExportPuzzleData(
        title=ch.name,
        rows=15,
        cols=15,
        grid=["#" * 15] * 15,
        entries=entries,
    )


def compute_project_page_plan(
    db: Session,
    project: Project,
    *,
    settings: Optional[dict[str, Any]] = None,
    latest_puzzle_by_col: Optional[dict[int, Puzzle]] = None,
) -> dict[str, Any]:
    """Compute exact page plan from actual export geometry for all chapters in the project."""
    norm_settings = settings or normalize_project_settings(project.settings, trim_size=project.trim_size)
    exp_settings = _project_export_settings(project, norm_settings)
    clue_cfg = norm_settings.get("clues") or {}
    page_cfg = norm_settings.get("page") or {}
    sol_cfg = norm_settings.get("solution") or {}
    cl_cfg = norm_settings.get("clue_layout") or {}
    title_cfg = norm_settings.get("title") or {}
    start_num = max(1, int(title_cfg.get("start_number", 1)))

    chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
    if latest_puzzle_by_col is None:
        chap_ids = [c.id for c in chapters]
        latest_puzzle_by_col = {}
        if chap_ids:
            for p in db.scalars(
                select(Puzzle)
                .where(Puzzle.collection_id.in_(chap_ids))
                .options(selectinload(Puzzle.entries))
                .order_by(Puzzle.id.asc())
            ).all():
                if p.collection_id is not None:
                    latest_puzzle_by_col[p.collection_id] = p

    chapter_puzzles: list[tuple[int, str, ExportPuzzleData]] = []
    for idx, ch in enumerate(chapters, start=1):
        puz_num = start_num + idx - 1
        exp_data = _chapter_export_data_for_plan(
            db,
            ch,
            latest_puzzle_by_col.get(ch.id),
            clue_mode=str(clue_cfg.get("mode") or "hybrid"),
            clue_diff=str(clue_cfg.get("difficulty") or "medium"),
        )
        puz_title = resolve_chapter_display_title(
            ch.name,
            puz_num,
            mode=str(title_cfg.get("mode") or "chapter_name"),
            template=str(title_cfg.get("template") or ""),
            enabled=bool(title_cfg.get("enabled", True)),
        )
        sol_title = resolve_chapter_display_title(
            ch.name,
            puz_num,
            mode=str(sol_cfg.get("title_mode") or "chapter_name"),
            template=str(sol_cfg.get("title_template") or ""),
            enabled=bool(sol_cfg.get("title_enabled", True)),
        )
        exp_data = ExportPuzzleData(
            title=puz_title,
            solution_title=sol_title,
            rows=exp_data.rows,
            cols=exp_data.cols,
            grid=exp_data.grid,
            entries=exp_data.entries,
        )
        chapter_puzzles.append((ch.id, ch.name, exp_data))

    return compute_book_page_plan(
        chapter_puzzles,
        exp_settings,
        solutions_per_page=int(sol_cfg.get("per_page", 4)),
        start_puzzles_on_right_hand_page=bool(page_cfg.get("start_puzzles_on_right_hand_page", False)),
        show_page_numbers=bool(page_cfg.get("show_page_numbers", True)),
        clue_placement=str(cl_cfg.get("placement") or "same_page"),
        font_dir=get_settings().font_dir,
    )


def stage_project_import(
    db: Session,
    project: Project,
    *,
    content_bytes: Optional[bytes] = None,
    text: Optional[str] = None,
    filename: Optional[str] = None,
    collection_name: Optional[str] = None,
    language: str = "en",
    first_line_is_title: Optional[bool] = None,
) -> ImportBatch:
    settings = normalize_project_settings(project.settings, trim_size=project.trim_size)
    grid_rows, grid_cols, max_grid_size, min_len = _grid_constraints(settings)
    max_len = int(settings.get("max_word_length", 30))
    expected_n = settings.get("words_per_chapter")
    if first_line_is_title is None:
        first_line_is_title = bool((settings.get("title") or {}).get("first_line_is_title", False))

    return stage_import(
        db,
        content_bytes=content_bytes,
        text=text,
        filename=filename,
        collection_name=collection_name,
        language=language,
        min_word_length=min_len,
        max_word_length=max_len,
        expected_words_per_chapter=expected_n,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        max_grid_size=max_grid_size,
        group_prefix="Chapter",
        project_id=project.id,
        first_line_is_title=bool(first_line_is_title),
    )


def accept_project_import(
    db: Session,
    project: Project,
    batch: ImportBatch,
    *,
    replace_existing: bool = True,
) -> dict[str, Any]:
    commit_res = commit_import(
        db,
        batch,
        project_id=project.id,
        replace_project_chapters=replace_existing,
    )
    report = batch.report or {}
    project.import_metadata = {
        "batch_id": batch.id,
        "filename": batch.filename,
        "source_format": batch.source_format,
        "total_rows": report.get("total_rows", 0),
        "valid_count": report.get("valid_count", 0),
        "duplicate_count": report.get("duplicate_count", 0),
        "invalid_count": report.get("invalid_count", 0),
        "empty_row_count": report.get("empty_row_count", 0),
        "warning_count": report.get("warning_count", 0),
        "skipped_header_count": report.get("skipped_header_count", 0),
        "extra_column_count": report.get("extra_column_count", 0),
        "skipped_headers": report.get("skipped_headers", []),
        "extra_columns": report.get("extra_columns", []),
        "warnings": report.get("warnings", []),
        "commit": commit_res,
    }
    project.updated_at = utcnow()
    db.commit()
    refreshed = get_project_or_404(db, project.id)
    return {
        "commit": commit_res,
        "project": serialize_project(db, refreshed),
    }


def export_project_json(db: Session, project_id: int) -> dict[str, Any]:
    project = get_project_or_404(db, project_id)
    chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
    chap_ids = [c.id for c in chapters]

    puzzles_by_col: dict[int, list[tuple[Puzzle, dict[int, str]]]] = {}
    if chap_ids:
        puzzles = list(
            db.scalars(
                select(Puzzle)
                .where(Puzzle.collection_id.in_(chap_ids))
                .options(selectinload(Puzzle.entries))
                .order_by(Puzzle.id.asc())
            ).all()
        )
        clue_ids = [e.clue_id for p in puzzles for e in p.entries if e.clue_id is not None]
        clue_text_by_id = {
            c.id: c.text
            for c in (db.scalars(select(Clue).where(Clue.id.in_(clue_ids))).all() if clue_ids else [])
        }
        for p in puzzles:
            if p.collection_id is not None:
                puzzles_by_col.setdefault(p.collection_id, []).append((p, clue_text_by_id))

    chapters_payload: list[dict[str, Any]] = []
    for ch in chapters:
        words_payload = []
        for link in ch.word_links:
            w = link.word
            words_payload.append(
                {
                    "position": link.position,
                    "answer": w.answer,
                    "display": link.display or w.display,
                    "raw_word": link.raw_word or (link.display or w.display),
                    "raw_clue": link.raw_clue,
                    "cell_ref": link.cell_ref,
                    "extra_data": list(link.extra_data or []),
                    "language": w.language,
                    "difficulty": w.difficulty,
                    "clues": [
                        {
                            "text": c.text,
                            "difficulty": c.difficulty,
                            "source": c.source,
                            "status": c.status,
                        }
                        for c in sorted(w.clues, key=lambda x: x.id)
                    ],
                }
            )

        puzzles_payload = []
        for p, clue_map in puzzles_by_col.get(ch.id, []):
            puzzles_payload.append(
                {
                    "title": p.title,
                    "status": p.status,
                    "clue_status": p.clue_status,
                    "rows": p.rows,
                    "cols": p.cols,
                    "grid": list(p.grid or []),
                    "settings": copy.deepcopy(p.settings or {}),
                    "validation": copy.deepcopy(p.validation or {}),
                    "unplaced": copy.deepcopy(p.unplaced or []),
                    "stats": copy.deepcopy(p.stats or {}),
                    "entries": [
                        {
                            "answer": e.answer,
                            "display": e.display,
                            "number": e.number,
                            "direction": e.direction,
                            "row": e.row,
                            "col": e.col,
                            "length": e.length,
                            "clue_text": clue_map.get(e.clue_id) if e.clue_id else None,
                        }
                        for e in sorted(p.entries, key=lambda x: (x.number, x.direction))
                    ],
                }
            )

        chapters_payload.append(
            {
                "name": ch.name,
                "chapter_index": ch.chapter_index,
                "language": ch.language,
                "chapter_meta": copy.deepcopy(ch.chapter_meta or {}),
                "words": words_payload,
                "puzzles": puzzles_payload,
            }
        )

    return {
        "schema_version": 1,
        "name": project.name,
        "project_type": project.project_type,
        "trim_size": project.trim_size,
        "current_step": project.current_step,
        "settings": normalize_project_settings(project.settings, trim_size=project.trim_size),
        "import_metadata": copy.deepcopy(project.import_metadata or {}),
        "chapters": chapters_payload,
    }


def restore_project_json(db: Session, data: dict[str, Any]) -> Project:
    trim_size = str(data.get("trim_size") or "6x9")
    settings = normalize_project_settings(data.get("settings"), trim_size=trim_size)
    project = Project(
        name=(str(data.get("name") or "Restored Crossword Book").strip() or "Restored Crossword Book"),
        project_type=str(data.get("project_type") or "crossword"),
        trim_size=trim_size,
        current_step=int(data.get("current_step") or 1),
        settings=settings,
        import_metadata=copy.deepcopy(data.get("import_metadata") or {}),
    )
    db.add(project)
    db.flush()

    for ch_idx, ch_data in enumerate(data.get("chapters") or []):
        ch_name = str(ch_data.get("name") or f"Chapter {ch_idx + 1}")
        ch_lang = str(ch_data.get("language") or "en")
        col = Collection(
            project_id=project.id,
            chapter_index=int(ch_data.get("chapter_index", ch_idx)),
            chapter_meta=copy.deepcopy(ch_data.get("chapter_meta") or {}),
            name=ch_name,
            language=ch_lang,
        )
        db.add(col)
        db.flush()

        word_by_answer: dict[str, Word] = {}
        clue_by_text: dict[tuple[int, str], Clue] = {}

        for w_pos, w_data in enumerate(ch_data.get("words") or []):
            answer = str(w_data.get("answer") or "").strip().upper()
            if not answer:
                continue
            disp = str(w_data.get("display") or answer)
            lang = str(w_data.get("language") or ch_lang)
            diff = w_data.get("difficulty")

            word = db.scalar(select(Word).where(Word.answer == answer, Word.language == lang))
            if word is None:
                word = Word(answer=answer, display=disp, language=lang, difficulty=diff)
                db.add(word)
                db.flush()
            elif word.display.upper() == word.answer and any(ch in disp for ch in (" ", "-", "–", "—")):
                word.display = disp

            word_by_answer[answer] = word
            first_clue_id: Optional[int] = None

            for c_data in w_data.get("clues") or []:
                c_text = str(c_data.get("text") or "").strip()
                if not c_text:
                    continue
                c_src = str(c_data.get("source") or "manual")
                c_stat = str(c_data.get("status") or "approved")
                c_diff = c_data.get("difficulty")
                existing_clue = db.scalar(
                    select(Clue).where(
                        Clue.word_id == word.id,
                        Clue.text == c_text,
                        Clue.source == c_src,
                    )
                )
                if existing_clue is None:
                    existing_clue = Clue(
                        word_id=word.id,
                        text=c_text,
                        difficulty=c_diff,
                        source=c_src,
                        status=c_stat,
                    )
                    db.add(existing_clue)
                    db.flush()
                clue_by_text[(word.id, c_text)] = existing_clue
                if first_clue_id is None:
                    first_clue_id = existing_clue.id

            db.add(
                CollectionWord(
                    collection_id=col.id,
                    word_id=word.id,
                    position=int(w_data.get("position", w_pos)),
                    display=disp,
                    raw_word=w_data.get("raw_word") or disp,
                    raw_clue=w_data.get("raw_clue"),
                    cell_ref=w_data.get("cell_ref"),
                    extra_data=list(w_data.get("extra_data") or []),
                    clue_id=first_clue_id,
                )
            )

        db.flush()
        for p_data in ch_data.get("puzzles") or []:
            entries_models: list[PuzzleEntry] = []
            for e_data in p_data.get("entries") or []:
                ans = str(e_data.get("answer") or "")
                w_obj = word_by_answer.get(ans)
                c_txt = e_data.get("clue_text")
                c_obj = clue_by_text.get((w_obj.id, c_txt)) if (w_obj and c_txt) else None
                entries_models.append(
                    PuzzleEntry(
                        word_id=w_obj.id if w_obj else None,
                        clue_id=c_obj.id if c_obj else None,
                        answer=ans,
                        display=e_data.get("display") or (w_obj.display if w_obj else ans),
                        number=int(e_data.get("number") or 1),
                        direction=str(e_data.get("direction") or "A"),
                        row=int(e_data.get("row") or 0),
                        col=int(e_data.get("col") or 0),
                        length=int(e_data.get("length") or len(ans)),
                    )
                )
            db.add(
                Puzzle(
                    collection_id=col.id,
                    title=str(p_data.get("title") or ch_name),
                    status=str(p_data.get("status") or "complete"),
                    clue_status=str(p_data.get("clue_status") or "complete"),
                    rows=int(p_data.get("rows") or 0),
                    cols=int(p_data.get("cols") or 0),
                    grid=list(p_data.get("grid") or []),
                    settings=copy.deepcopy(p_data.get("settings") or {}),
                    validation=copy.deepcopy(p_data.get("validation") or {}),
                    unplaced=copy.deepcopy(p_data.get("unplaced") or []),
                    stats=copy.deepcopy(p_data.get("stats") or {}),
                    entries=entries_models,
                )
            )

    db.commit()
    return get_project_or_404(db, project.id)


def apply_chapter_inline_action(
    db: Session,
    project_id: int,
    chapter_id: int,
    *,
    action: str,
    old_word: Optional[str] = None,
    new_word: Optional[str] = None,
    clue: Optional[str] = None,
    seed: Optional[int] = None,
    rows: Optional[int] = None,
    cols: Optional[int] = None,
    max_size: Optional[int] = None,
    auto_retry: bool = False,
) -> dict[str, Any]:
    """Execute an inline recovery action on a chapter and regenerate its puzzle."""
    project = get_project_or_404(db, project_id)
    chapter = next((c for c in project.chapters if c.id == chapter_id), None)
    if chapter is None:
        raise LookupError(f"Chapter {chapter_id} not found in project {project_id}")

    settings = normalize_project_settings(project.settings, trim_size=project.trim_size)
    clue_cfg = settings.get("clues") or {}
    grid_cfg = dict(settings.get("grid") or {})
    clue_mode = clue_cfg.get("mode", "hybrid")
    clue_diff = clue_cfg.get("difficulty", "medium")
    min_density = float(grid_cfg.get("min_density", 0.15))

    latest_puzzle = db.scalar(
        select(Puzzle)
        .where(Puzzle.collection_id == chapter.id)
        .options(selectinload(Puzzle.entries))
        .order_by(Puzzle.id.desc())
    )
    latest_eng = dict((latest_puzzle.settings or {}).get("engine") or {}) if latest_puzzle else {}

    meta = dict(chapter.chapter_meta or {})
    grid_override = dict(meta.get("grid_override") or {})

    if action == "edit_word":
        if not old_word or not new_word:
            raise ValueError("edit_word requires old_word and new_word")
        old_norm, _ = normalize_answer(old_word)
        old_key = old_norm or old_word.strip().upper()
        target_link = next(
            (lnk for lnk in chapter.word_links if lnk.word.answer == old_key),
            None,
        )
        if target_link is None:
            raise LookupError(f"Word '{old_word}' not found in chapter '{chapter.name}'")
        new_w = _ensure_word(
            db,
            new_word,
            language=chapter.language,
            clue_text=clue,
            difficulty=clue_diff,
        )
        existing_dup = next(
            (
                lnk
                for lnk in chapter.word_links
                if lnk.word_id == new_w.id and lnk.id != target_link.id
            ),
            None,
        )
        if existing_dup is not None:
            db.delete(target_link)
        else:
            target_link.word_id = new_w.id
            target_link.word = new_w
            target_link.display = new_word.strip()
            target_link.raw_word = new_word.strip()
            if clue and clue.strip():
                target_link.raw_clue = clue.strip()
                active = resolve_clue_for_word(new_w.clues, mode="hybrid", difficulty=clue_diff)
                target_link.clue_id = active.id if active else None
            else:
                target_link.clue_id = None
        meta.pop("unplaced_words", None)
        chapter.chapter_meta = meta
        db.flush()
        db.expire_all()

    elif action == "remove_word":
        target_raw = old_word or new_word
        if not target_raw:
            raise ValueError("remove_word requires old_word")
        rem_norm, _ = normalize_answer(target_raw)
        rem_key = rem_norm or target_raw.strip().upper()
        target_link = next(
            (lnk for lnk in chapter.word_links if lnk.word.answer == rem_key),
            None,
        )
        if target_link is None:
            raise LookupError(f"Word '{target_raw}' not found in chapter '{chapter.name}'")
        remaining = [lnk for lnk in chapter.word_links if lnk.id != target_link.id]
        if not remaining:
            raise ValueError("Cannot remove the last word from a chapter")
        db.delete(target_link)
        for pos, lnk in enumerate(remaining):
            lnk.position = pos
        meta.pop("unplaced_words", None)
        chapter.chapter_meta = meta
        db.flush()
        db.expire_all()

    elif action == "larger_grid":
        eff_mode = grid_override.get("mode") or grid_cfg.get("mode", "auto")
        if rows is not None and cols is not None:
            grid_override["mode"] = "custom"
            grid_override["rows"] = rows
            grid_override["cols"] = cols
        elif eff_mode == "custom" or (latest_eng.get("rows") and latest_eng.get("cols")):
            cur_r = int(grid_override.get("rows") or latest_eng.get("rows") or grid_cfg.get("rows") or 15)
            cur_c = int(grid_override.get("cols") or latest_eng.get("cols") or grid_cfg.get("cols") or 15)
            grid_override["mode"] = "custom"
            grid_override["rows"] = min(60, cur_r + 4)
            grid_override["cols"] = min(60, cur_c + 4)
        else:
            cur_max = int(
                max_size
                or grid_override.get("max_size")
                or latest_eng.get("max_size")
                or grid_cfg.get("max_size")
                or 40
            )
            grid_override["max_size"] = min(60, cur_max + 6)
        meta["grid_override"] = grid_override
        chapter.chapter_meta = meta
        db.flush()

    elif action in ("new_seed", "auto_retry", "reproduce"):
        pass
    else:
        raise ValueError(f"Unsupported inline action '{action}'")

    eff_mode = grid_override.get("mode") or grid_cfg.get("mode", "auto")
    eff_rows = (
        int(grid_override.get("rows") or latest_eng.get("rows") or grid_cfg.get("rows") or 15)
        if eff_mode == "custom"
        else None
    )
    eff_cols = (
        int(grid_override.get("cols") or latest_eng.get("cols") or grid_cfg.get("cols") or 15)
        if eff_mode == "custom"
        else None
    )
    eff_max_size = int(
        grid_override.get("max_size") or latest_eng.get("max_size") or grid_cfg.get("max_size") or 40
    )
    cur_seed = int(latest_eng.get("seed") if latest_eng.get("seed") is not None else grid_cfg.get("seed", 1))
    win_seed = meta.get("winning_seed") or (latest_puzzle.settings if latest_puzzle else {}).get("winning_seed")
    win_strategy = (
        meta.get("winning_strategy")
        or (latest_puzzle.settings if latest_puzzle else {}).get("winning_strategy")
        or latest_eng.get("strategy")
        or grid_cfg.get("strategy", "auto")
    )

    if action == "reproduce":
        eff_seed = int(win_seed if win_seed is not None else cur_seed)
        eff_strategy = str(win_strategy or "auto")
    elif seed is not None:
        eff_seed = int(seed)
        eff_strategy = str(latest_eng.get("strategy") or grid_cfg.get("strategy", "auto"))
    elif action in ("new_seed", "auto_retry"):
        eff_seed = cur_seed + 1
        eff_strategy = str(latest_eng.get("strategy") or grid_cfg.get("strategy", "auto"))
    else:
        eff_seed = cur_seed
        eff_strategy = str(latest_eng.get("strategy") or grid_cfg.get("strategy", "auto"))

    eng_cfg = EngineSettings(
        rows=eff_rows,
        cols=eff_cols,
        max_size=eff_max_size,
        seed=eff_seed,
        symmetry=str(grid_cfg.get("symmetry", "off")),
        min_word_length=int(grid_cfg.get("min_word_length", settings.get("min_word_length", 3))),
        strategy=eff_strategy,
    )

    eff_auto_retry = False if action == "reproduce" else bool(
        auto_retry or action in ("auto_retry", "edit_word", "remove_word", "larger_grid")
    )
    puzzle = generate_and_save_puzzle(
        db,
        collection_id=chapter.id,
        title=chapter.name,
        engine_settings=eng_cfg,
        clue_mode=clue_mode,
        difficulty=clue_diff,
        min_density=min_density,
        auto_retry=eff_auto_retry,
        max_retries=3,
    )
    project.updated_at = utcnow()
    db.commit()

    refreshed_project = get_project_or_404(db, project_id)
    serialized_proj = serialize_project(db, refreshed_project)
    serialized_ch = next((c for c in serialized_proj["chapters"] if c["id"] == chapter_id), None)
    return {
        "chapter": serialized_ch,
        "puzzle": serialize_puzzle(db, puzzle),
        "project": serialized_proj,
    }


def _project_pdf_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (name or "crossword_book").strip()).strip("_").lower()
    return f"{slug or 'crossword_book'}.pdf"


def _book_pdf_storage_path(project_id: int) -> Path:
    out_dir = Path("data") / "books"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"project_{project_id}.pdf"


def _chapter_engine_dict(
    project: Project,
    ch: Collection,
    *,
    seed_offset: int = 0,
) -> tuple[dict[str, Any], str, str, float, int]:
    settings = normalize_project_settings(project.settings, trim_size=project.trim_size)
    clue_cfg = settings.get("clues") or {}
    grid_cfg = dict(settings.get("grid") or {})
    meta = dict(ch.chapter_meta or {})
    grid_override = dict(meta.get("grid_override") or {})

    eff_mode = grid_override.get("mode") or grid_cfg.get("mode", "auto")
    eff_rows = int(grid_override.get("rows") or grid_cfg.get("rows") or 15) if eff_mode == "custom" else None
    eff_cols = int(grid_override.get("cols") or grid_cfg.get("cols") or 15) if eff_mode == "custom" else None
    eff_max = int(grid_override.get("max_size") or grid_cfg.get("max_size") or 40)
    max_retries = max(0, min(5, int(grid_cfg.get("max_retries", 2))))

    eng_cfg = EngineSettings(
        rows=eff_rows,
        cols=eff_cols,
        max_size=eff_max,
        seed=int(grid_cfg.get("seed", 1)) + seed_offset,
        symmetry=str(grid_cfg.get("symmetry", "off")),
        min_word_length=int(grid_cfg.get("min_word_length", settings.get("min_word_length", 3))),
        strategy=str(grid_cfg.get("strategy", "auto")),
    )
    from dataclasses import asdict

    return (
        asdict(eng_cfg),
        str(clue_cfg.get("mode") or "hybrid"),
        str(clue_cfg.get("difficulty") or "medium"),
        float(grid_cfg.get("min_density", 0.15)),
        max_retries,
    )


def _generate_chapter_puzzle_for_project(
    db: Session,
    project: Project,
    ch: Collection,
    *,
    seed_offset: int = 0,
) -> Puzzle:
    eng_dict, clue_mode, difficulty, min_density, max_retries = _chapter_engine_dict(
        project, ch, seed_offset=seed_offset
    )
    return generate_and_save_puzzle(
        db,
        collection_id=ch.id,
        title=ch.name,
        engine_settings=EngineSettings(**eng_dict),
        clue_mode=clue_mode,
        difficulty=difficulty,
        min_density=min_density,
        auto_retry=True,
        max_retries=max_retries,
    )


def _persist_chapter_bundle(
    db: Session,
    ch: Collection,
    bundle: dict[str, Any],
    *,
    eng_dict: dict[str, Any],
    clue_mode: str,
    difficulty: str,
) -> Puzzle:
    res_dict = bundle["result"]
    quality = bundle["quality"]
    win_seed = bundle["winning_seed"]
    win_strategy = bundle["winning_strategy"]
    retry_history = bundle["retry_history"]
    hit_tl = bundle["hit_time_limit"]

    link_by_ans: dict[str, CollectionWord] = {}
    for lnk in ch.word_links:
        if lnk.word.answer not in link_by_ans:
            link_by_ans[lnk.word.answer] = lnk

    entries_models: list[PuzzleEntry] = []
    retained_map: dict[str, int] = {}
    missing_clues = 0
    for e in res_dict["entries"]:
        lnk = link_by_ans.get(e["answer"])
        w = lnk.word if lnk else None
        clue_id: Optional[int] = None
        if w is not None:
            active = resolve_clue_for_word(
                w.clues,
                mode=clue_mode,
                difficulty=difficulty,
                preferred_clue_id=lnk.clue_id if lnk else None,
            )
            if active is not None:
                clue_id = active.id
                retained_map[e["answer"]] = clue_id
        if clue_id is None:
            missing_clues += 1
        entries_models.append(
            PuzzleEntry(
                word_id=w.id if w else None,
                clue_id=clue_id,
                answer=e["answer"],
                display=(lnk.display or w.display) if (lnk and w) else e["answer"],
                number=e["number"],
                direction=e["direction"],
                row=e["row"],
                col=e["col"],
                length=len(e["answer"]),
            )
        )

    clue_status = "complete" if (missing_clues == 0 and len(entries_models) > 0) else "incomplete"
    grid_strings = ["".join(c or "#" for c in row) for row in res_dict["cells"]]
    needs_attention = not quality["meets_threshold"]
    persisted_status = "Needs attention" if needs_attention else res_dict["status"]

    stored_eng = dict(eng_dict)
    stored_eng["seed"] = win_seed
    stored_eng["strategy"] = win_strategy

    puzzle = Puzzle(
        collection_id=ch.id,
        title=ch.name,
        status=persisted_status,
        clue_status=clue_status,
        rows=res_dict["rows"],
        cols=res_dict["cols"],
        grid=grid_strings,
        settings={
            "engine": stored_eng,
            "clue_mode": clue_mode,
            "difficulty": difficulty,
            "retained_clues": retained_map,
            "word_ids": [lnk.word_id for lnk in ch.word_links],
            "winning_seed": win_seed,
            "winning_strategy": win_strategy,
            "quality": quality,
            "retry_history": retry_history,
        },
        validation=res_dict["validation"],
        unplaced=res_dict["unplaced"],
        stats=res_dict["stats"],
        entries=entries_models,
    )
    db.add(puzzle)
    db.flush()

    meta = dict(ch.chapter_meta or {})
    meta["winning_seed"] = win_seed
    meta["winning_strategy"] = win_strategy
    meta["quality"] = quality
    meta["unplaced_words"] = res_dict["unplaced"]
    meta["hit_time_limit"] = hit_tl
    meta["status"] = quality["status"]
    ch.chapter_meta = meta
    db.flush()
    return puzzle


def build_project_book_pdf(
    db: Session,
    project: Project,
    *,
    auto_generate_missing_puzzles: bool = True,
) -> tuple[bytes, dict[str, Any], dict[str, Any], str]:
    """Assemble and verify a complete project book PDF. Refuses partial or blocked books."""
    serialized = serialize_project(db, project)
    if not serialized["can_generate_and_download"]:
        msgs = [b["message"] for b in serialized["blocking_issues"]]
        raise PermissionError("Cannot build book PDF: " + " ".join(msgs))

    chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
    chap_ids = [c.id for c in chapters]
    latest_by_col: dict[int, Puzzle] = {}
    if chap_ids:
        for p in db.scalars(
            select(Puzzle)
            .where(Puzzle.collection_id.in_(chap_ids))
            .options(selectinload(Puzzle.entries))
            .order_by(Puzzle.id.asc())
        ).all():
            if p.collection_id is not None:
                latest_by_col[p.collection_id] = p

    for ch in chapters:
        puz = latest_by_col.get(ch.id)
        if puz is None and auto_generate_missing_puzzles:
            puz = _generate_chapter_puzzle_for_project(db, project, ch)
            latest_by_col[ch.id] = puz

    # Re-check blocking issues after ensuring every chapter has a generated puzzle
    refreshed_proj = get_project_or_404(db, project.id)
    refreshed_ser = serialize_project(db, refreshed_proj)
    if not refreshed_ser["can_generate_and_download"]:
        msgs = [b["message"] for b in refreshed_ser["blocking_issues"]]
        raise PermissionError("Cannot build book PDF (no partial books): " + " ".join(msgs))

    settings = normalize_project_settings(refreshed_proj.settings, trim_size=refreshed_proj.trim_size)
    exp_settings = _project_export_settings(refreshed_proj, settings)
    page_cfg = settings.get("page") or {}
    sol_cfg = settings.get("solution") or {}
    cl_cfg = settings.get("clue_layout") or {}
    title_cfg = settings.get("title") or {}
    start_num = max(1, int(title_cfg.get("start_number", 1)))

    chapter_puzzles: list[tuple[int, str, ExportPuzzleData]] = []
    for idx, ch in enumerate(sorted(refreshed_proj.chapters, key=lambda c: (c.chapter_index, c.id)), start=1):
        puz = latest_by_col.get(ch.id)
        if puz is None or puz.status in ("invalid", "empty", "Needs attention"):
            raise PermissionError(f"Chapter '{ch.name}' has not succeeded; refusing partial book.")
        puz_num = start_num + idx - 1
        exp_data = build_puzzle_export_data(db, puz, force=False)
        puz_title = resolve_chapter_display_title(
            ch.name,
            puz_num,
            mode=str(title_cfg.get("mode") or "chapter_name"),
            template=str(title_cfg.get("template") or ""),
            enabled=bool(title_cfg.get("enabled", True)),
        )
        sol_title = resolve_chapter_display_title(
            ch.name,
            puz_num,
            mode=str(sol_cfg.get("title_mode") or "chapter_name"),
            template=str(sol_cfg.get("title_template") or ""),
            enabled=bool(sol_cfg.get("title_enabled", True)),
        )
        exp_data = ExportPuzzleData(
            title=puz_title,
            solution_title=sol_title,
            rows=exp_data.rows,
            cols=exp_data.cols,
            grid=exp_data.grid,
            entries=exp_data.entries,
        )
        chapter_puzzles.append((ch.id, ch.name, exp_data))

    pdf_bytes, page_plan, verification = build_book_pdf(
        chapter_puzzles,
        exp_settings,
        solutions_per_page=int(sol_cfg.get("per_page", 4)),
        start_puzzles_on_right_hand_page=bool(page_cfg.get("start_puzzles_on_right_hand_page", False)),
        show_page_numbers=bool(page_cfg.get("show_page_numbers", True)),
        clue_placement=str(cl_cfg.get("placement") or "same_page"),
        font_dir=get_settings().font_dir,
        verify=True,
    )
    storage_path = _book_pdf_storage_path(refreshed_proj.id)
    storage_path.write_bytes(pdf_bytes)
    return pdf_bytes, page_plan, verification, _project_pdf_slug(refreshed_proj.name)


def create_book_generation_job(
    db: Session,
    project_id: int,
    *,
    regenerate: bool = False,
) -> Job:
    """Validate project pre-conditions and enqueue a background book build job."""
    project = get_project_or_404(db, project_id)
    serialized = serialize_project(db, project)
    if not serialized["can_generate_and_download"]:
        msgs = [b["message"] for b in serialized["blocking_issues"]]
        raise PermissionError("Cannot generate and download: " + " ".join(msgs))

    chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
    job = Job(
        id=uuid.uuid4().hex,
        type="book_generate_and_download",
        status="pending",
        total=len(chapters) + 1,
        completed=0,
        failed=0,
        payload={
            "project_id": project.id,
            "chapter_ids": [c.id for c in chapters],
            "regenerate": bool(regenerate),
            "cancel_requested": False,
        },
        result={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def execute_book_generation_job(
    job_id: str,
    session_factory: Callable[[], Session],
) -> None:
    """Run per-chapter puzzle generation with Phase 2 retries, then build and verify the book PDF."""
    t_start = time.perf_counter()
    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
            job.status = "cancelled"
            db.commit()
            return

        payload = dict(job.payload or {})
        project_id = int(payload["project_id"])
        regenerate = bool(payload.get("regenerate", False))
        job.status = "running"
        db.commit()

        try:
            project = get_project_or_404(db, project_id)
            chapters = sorted(project.chapters, key=lambda c: (c.chapter_index, c.id))
            chap_ids = [c.id for c in chapters]
            latest_by_col: dict[int, Puzzle] = {}
            if chap_ids:
                for p in db.scalars(
                    select(Puzzle).where(Puzzle.collection_id.in_(chap_ids)).order_by(Puzzle.id.asc())
                ).all():
                    if p.collection_id is not None:
                        latest_by_col[p.collection_id] = p

            failed_chapters: list[dict[str, Any]] = []
            pending_chapters: list[Collection] = []
            total_retries_used = 0

            for ch in chapters:
                db.refresh(job)
                if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                    job.status = "cancelled"
                    db.commit()
                    return

                existing = latest_by_col.get(ch.id)
                if existing is not None and not regenerate and existing.status not in ("invalid", "empty", "Needs attention"):
                    job.completed += 1
                    db.commit()
                else:
                    pending_chapters.append(ch)

            if len(pending_chapters) >= 4:
                max_workers = max(2, min(4, os.cpu_count() or 2))
                pool: Optional[ProcessPoolExecutor] = None
                try:
                    pool = ProcessPoolExecutor(max_workers=max_workers)
                except Exception:
                    pool = None

                try:
                    batch_size = max_workers * 2
                    for offset in range(0, len(pending_chapters), batch_size):
                        db.refresh(job)
                        if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                            job.status = "cancelled"
                            db.commit()
                            return

                        batch = pending_chapters[offset : offset + batch_size]
                        work_items: list[tuple[Collection, list[str], dict[str, Any], str, str, float, int, Any]] = []
                        for ch in batch:
                            eng_dict, clue_mode, diff, min_density, max_retries = _chapter_engine_dict(
                                project, ch
                            )
                            answers = list(dict.fromkeys(lnk.word.answer for lnk in ch.word_links))
                            fut = (
                                pool.submit(
                                    _run_chapter_with_retries,
                                    answers,
                                    eng_dict,
                                    min_density,
                                    None,
                                    True,
                                    max_retries,
                                )
                                if pool is not None
                                else None
                            )
                            work_items.append((ch, answers, eng_dict, clue_mode, diff, min_density, max_retries, fut))

                        for ch, answers, eng_dict, clue_mode, diff, min_density, max_retries, fut in work_items:
                            db.refresh(job)
                            if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                                for _, _, _, _, _, _, _, pf in work_items:
                                    if pf is not None:
                                        pf.cancel()
                                job.status = "cancelled"
                                db.commit()
                                return

                            bundle = (
                                fut.result()
                                if fut is not None
                                else _run_chapter_with_retries(
                                    answers,
                                    eng_dict,
                                    min_density=min_density,
                                    auto_retry=True,
                                    max_retries=max_retries,
                                )
                            )
                            total_retries_used += max(0, int(bundle.get("attempts_tried", 1)) - 1)
                            puz = _persist_chapter_bundle(
                                db,
                                ch,
                                bundle,
                                eng_dict=eng_dict,
                                clue_mode=clue_mode,
                                difficulty=diff,
                            )
                            if puz.status in ("invalid", "empty", "Needs attention") or puz.unplaced:
                                job.failed += 1
                                failed_chapters.append(
                                    {"chapter_id": ch.id, "chapter_name": ch.name, "status": puz.status}
                                )
                            else:
                                job.completed += 1
                        db.commit()
                finally:
                    if pool is not None:
                        pool.shutdown(wait=True)
            else:
                for ch in pending_chapters:
                    db.refresh(job)
                    if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                        job.status = "cancelled"
                        db.commit()
                        return
                    puz = _generate_chapter_puzzle_for_project(db, project, ch)
                    hist = (puz.settings or {}).get("retry_history") or []
                    total_retries_used += max(0, len(hist) - 1)
                    if puz.status in ("invalid", "empty", "Needs attention") or puz.unplaced:
                        job.failed += 1
                        failed_chapters.append(
                            {"chapter_id": ch.id, "chapter_name": ch.name, "status": puz.status}
                        )
                    else:
                        job.completed += 1
                    db.commit()

            if failed_chapters:
                refreshed = get_project_or_404(db, project_id)
                ser = serialize_project(db, refreshed)
                job.status = "failed"
                job.error = "Some chapters need attention; refusing to build a partial book."
                job.result = {
                    "failed_chapters": failed_chapters,
                    "blocking_issues": ser["blocking_issues"],
                    "total_retries_used": total_retries_used,
                    "elapsed_seconds": round(time.perf_counter() - t_start, 3),
                }
                db.commit()
                return

            db.refresh(job)
            if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                job.status = "cancelled"
                db.commit()
                return

            refreshed = get_project_or_404(db, project_id)
            _pdf_bytes, page_plan, verification, filename = build_project_book_pdf(
                db, refreshed, auto_generate_missing_puzzles=False
            )
            job.completed = job.total
            job.status = "completed"
            job.result = {
                "filename": filename,
                "download_url": f"/api/projects/{project_id}/download-pdf",
                "page_plan": page_plan,
                "verification": verification,
                "total_retries_used": total_retries_used,
                "elapsed_seconds": round(time.perf_counter() - t_start, 3),
            }
            db.commit()
        except (PermissionError, PDFVerificationError, Exception) as exc:
            job.status = "failed"
            job.error = redact_secrets(str(exc))
            db.commit()


def retry_failed_project_chapters(db: Session, project_id: int) -> dict[str, Any]:
    """Re-run Phase 2 retry logic on all failed / Needs attention chapters in a project."""
    project = get_project_or_404(db, project_id)
    serialized = serialize_project(db, project)
    retried = 0
    for ch_info in serialized["chapters"]:
        if ch_info["status"] in ("Needs attention", "Words won't fit") or ch_info["puzzle_id"] is None:
            ch_obj = next((c for c in project.chapters if c.id == ch_info["id"]), None)
            if ch_obj is not None:
                cur_seed = int(ch_info.get("winning_seed") or 1)
                _generate_chapter_puzzle_for_project(db, project, ch_obj, seed_offset=cur_seed + 1)
                retried += 1
    project.updated_at = utcnow()
    db.commit()
    refreshed = get_project_or_404(db, project_id)
    return {
        "retried_chapters": retried,
        "project": serialize_project(db, refreshed),
    }


