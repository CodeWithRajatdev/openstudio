"""Puzzle persistence, validation re-check, single-clue editing, regeneration, and export."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..engine import (
    EngineSettings,
    PlacedEntry,
    WordInput,
    format_enumeration,
    generate_crossword,
    normalize_answer,
    validate_grid,
)
from ..models import Clue, Collection, CollectionWord, Project, Puzzle, PuzzleEntry, Word
from .clues.service import resolve_clue_for_word
from .export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from .export.renderers import render_pdf, render_png, render_svg
from .export.settings import ExportSettings
from .quality import (
    build_plain_language_diagnostics,
    build_retry_schedule,
    compute_grid_quality_metrics,
    evaluate_quality_threshold,
)


def _ensure_word(
    db: Session,
    raw_word: str,
    *,
    language: str = "en",
    clue_text: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> Word:
    answer, problem = normalize_answer(raw_word)
    if problem or not answer:
        raise ValueError(f"Invalid word '{raw_word}': {problem}")

    word = db.scalar(
        select(Word)
        .where(Word.answer == answer, Word.language == language)
        .options(selectinload(Word.clues))
    )
    if word is None:
        word = Word(answer=answer, display=raw_word.strip(), language=language, difficulty=difficulty)
        db.add(word)
        db.flush()
        word.clues = []
    elif word.display.upper() == word.answer and any(ch in raw_word.strip() for ch in (" ", "-", "–", "—")):
        word.display = raw_word.strip()

    if clue_text and clue_text.strip():
        cleaned_clue = clue_text.strip()
        existing = next(
            (c for c in word.clues if c.text == cleaned_clue and c.source in ("manual", "import")),
            None,
        )
        if existing is None:
            new_clue = Clue(
                word_id=word.id,
                text=cleaned_clue,
                difficulty=difficulty,
                source="manual",
                status="approved",
            )
            db.add(new_clue)
            db.flush()
            word.clues.append(new_clue)

    return word


def recheck_puzzle_validity(puzzle: Puzzle, entries: list[PuzzleEntry]) -> tuple[bool, list[str]]:
    """Independently re-validate a stored puzzle before export."""
    if not puzzle.grid or puzzle.rows <= 0 or puzzle.cols <= 0:
        return False, ["puzzle grid is empty"]

    cells: list[list[Optional[str]]] = [
        [None if ch == "#" else ch for ch in row_str] for row_str in puzzle.grid
    ]
    placed = [
        PlacedEntry(
            answer=e.answer,
            row=e.row,
            col=e.col,
            direction=e.direction,
            ref=e.word_id,
            number=e.number,
        )
        for e in entries
    ]
    unplaced_answers = [u.get("answer") for u in (puzzle.unplaced or []) if isinstance(u, dict) and u.get("answer")]
    all_supplied = [e.answer for e in entries] + unplaced_answers
    report = validate_grid(
        cells,
        placed,
        expected=all_supplied,
        unplaced=unplaced_answers,
    )
    return report.valid, report.errors


def serialize_puzzle(
    db: Session,
    puzzle: Puzzle,
    *,
    enumeration_display: Optional[str] = None,
) -> dict[str, Any]:
    entries = sorted(puzzle.entries, key=lambda e: (e.number, e.direction))
    clue_ids = [e.clue_id for e in entries if e.clue_id is not None]
    clues_by_id: dict[int, Clue] = {}
    if clue_ids:
        for c in db.scalars(select(Clue).where(Clue.id.in_(clue_ids))).all():
            clues_by_id[c.id] = c

    word_ids = [e.word_id for e in entries if e.word_id is not None]
    words_by_id: dict[int, Word] = {}
    if word_ids:
        for w in db.scalars(select(Word).where(Word.id.in_(word_ids))).all():
            words_by_id[w.id] = w

    eff_enum_display = enumeration_display
    if eff_enum_display is None and puzzle.collection_id is not None:
        col = db.get(Collection, puzzle.collection_id)
        if col is not None and col.project_id is not None:
            proj = db.get(Project, col.project_id)
            if proj is not None and isinstance(proj.settings, dict):
                eff_enum_display = proj.settings.get("enumeration_display")
    if not eff_enum_display:
        eff_enum_display = "formatted"

    entries_out = []
    missing_clues = []
    for e in entries:
        c = clues_by_id.get(e.clue_id) if e.clue_id else None
        w = words_by_id.get(e.word_id) if e.word_id else None
        if c is None:
            missing_clues.append(e.answer)
        disp = e.display or (w.display if w else e.answer)
        entries_out.append(
            {
                "id": e.id,
                "word_id": e.word_id,
                "clue_id": e.clue_id,
                "answer": e.answer,
                "display": disp,
                "enumeration": format_enumeration(e.answer, disp, style=eff_enum_display),
                "number": e.number,
                "direction": e.direction,
                "row": e.row,
                "col": e.col,
                "length": e.length,
                "clue": c.text if c else None,
                "clue_source": c.source if c else None,
                "clue_status": c.status if c else None,
            }
        )

    stored_settings = puzzle.settings or {}
    stored_quality = stored_settings.get("quality") or {}
    min_density = float(stored_quality.get("min_density", 0.15))
    min_crossings = stored_quality.get("min_crossings")
    metrics = compute_grid_quality_metrics(puzzle.grid or [], entries_out, puzzle.unplaced or [])
    quality = evaluate_quality_threshold(
        metrics,
        validation_valid=bool((puzzle.validation or {}).get("valid", True)),
        min_density=min_density,
        min_crossings=min_crossings,
    )
    diagnostics = build_plain_language_diagnostics(
        validation=puzzle.validation,
        unplaced=puzzle.unplaced or [],
        quality=quality,
        stats=puzzle.stats,
        missing_clues=missing_clues,
    )
    winning_seed = stored_settings.get("winning_seed", (stored_settings.get("engine") or {}).get("seed", 0))
    winning_strategy = stored_settings.get(
        "winning_strategy", (stored_settings.get("engine") or {}).get("strategy", "auto")
    )

    return {
        "id": puzzle.id,
        "collection_id": puzzle.collection_id,
        "title": puzzle.title,
        "status": puzzle.status,
        "quality_status": quality["status"],
        "needs_attention": diagnostics["needs_attention"],
        "clue_status": puzzle.clue_status,
        "missing_clues": missing_clues,
        "rows": puzzle.rows,
        "cols": puzzle.cols,
        "grid": puzzle.grid,
        "entries": entries_out,
        "unplaced": puzzle.unplaced,
        "validation": puzzle.validation,
        "stats": puzzle.stats,
        "settings": puzzle.settings,
        "quality": quality,
        "diagnostics": diagnostics,
        "plain_errors": diagnostics["messages"],
        "winning_seed": winning_seed,
        "winning_strategy": winning_strategy,
        "hit_time_limit": diagnostics["hit_time_limit"],
        "retry_history": stored_settings.get("retry_history", []),
        "created_at": puzzle.created_at.isoformat() if puzzle.created_at else None,
        "updated_at": puzzle.updated_at.isoformat() if puzzle.updated_at else None,
    }


def _run_engine_with_optional_retries(
    word_inputs: list[WordInput],
    eng_cfg: EngineSettings,
    *,
    min_density: float = 0.15,
    min_crossings: Optional[int] = None,
    auto_retry: bool = False,
    max_retries: int = 3,
):
    schedule = build_retry_schedule(
        base_seed=eng_cfg.seed,
        base_strategy=eng_cfg.strategy,
        max_retries=max_retries if auto_retry else 0,
    )
    base_dict = asdict(eng_cfg)
    best_bundle = None
    retry_history: list[dict[str, Any]] = []
    any_hit_tl = False

    for try_seed, try_strategy in schedule:
        cand_cfg = EngineSettings(**{**base_dict, "seed": try_seed, "strategy": try_strategy})
        res = generate_crossword(word_inputs, cand_cfg)
        if res.status == "invalid" or not res.validation.valid:
            raise RuntimeError(f"Engine produced an invalid grid: {res.validation.errors}")
        grid_strings = ["".join(c or "#" for c in row) for row in res.cells]
        metrics = compute_grid_quality_metrics(grid_strings, res.entries, res.unplaced)
        quality = evaluate_quality_threshold(
            metrics,
            validation_valid=res.validation.valid,
            min_density=min_density,
            min_crossings=min_crossings,
        )
        hit_tl = bool((res.stats or {}).get("hit_time_limit"))
        if hit_tl:
            any_hit_tl = True
        retry_history.append(
            {
                "seed": try_seed,
                "strategy": try_strategy,
                "placed_count": quality["placed_count"],
                "unplaced_count": quality["unplaced_count"],
                "density": quality["density"],
                "crossing_count": quality["crossing_count"],
                "meets_threshold": quality["meets_threshold"],
                "hit_time_limit": hit_tl,
            }
        )
        rank = (
            1 if quality["meets_threshold"] else 0,
            quality["placed_count"],
            -quality["unplaced_count"],
            round(quality["density"], 4),
            quality["crossing_count"],
            -quality["total_cells"],
        )
        if best_bundle is None or rank > best_bundle[0]:
            best_bundle = (rank, res, grid_strings, quality, cand_cfg, try_seed, try_strategy)
        if quality["meets_threshold"]:
            break

    assert best_bundle is not None
    _, best_res, best_grid, best_quality, best_cfg, win_seed, win_strategy = best_bundle
    if any_hit_tl:
        best_res.stats = {**(best_res.stats or {}), "hit_time_limit": True}
    return best_res, best_grid, best_quality, best_cfg, win_seed, win_strategy, retry_history


def generate_and_save_puzzle(
    db: Session,
    *,
    collection_id: Optional[int] = None,
    words: Optional[list[Word]] = None,
    title: Optional[str] = None,
    engine_settings: Optional[EngineSettings] = None,
    clue_mode: str = "hybrid",
    difficulty: str = "medium",
    retained_clues: Optional[dict[str, int]] = None,
    min_density: float = 0.15,
    min_crossings: Optional[int] = None,
    auto_retry: bool = False,
    max_retries: int = 3,
) -> Puzzle:
    eng_cfg = engine_settings or EngineSettings()

    display_by_answer: dict[str, str] = {}
    preferred_clue_by_answer: dict[str, int] = {}
    col_obj: Optional[Collection] = None
    if words is None:
        if collection_id is None:
            raise ValueError("Provide either collection_id or words")
        col = db.scalar(
            select(Collection)
            .where(Collection.id == collection_id)
            .options(
                selectinload(Collection.word_links)
                .selectinload(CollectionWord.word)
                .selectinload(Word.clues)
            )
        )
        if col is None:
            raise LookupError(f"Collection {collection_id} not found")
        col_obj = col
        words = [link.word for link in col.word_links]
        for link in col.word_links:
            display_by_answer[link.word.answer] = link.display or link.word.display
            if link.clue_id is not None:
                preferred_clue_by_answer[link.word.answer] = link.clue_id
        if not title:
            title = col.name
    else:
        for w in words:
            display_by_answer[w.answer] = w.display
        if collection_id is not None:
            col_obj = db.get(Collection, collection_id)

    if not words:
        raise ValueError("Cannot generate a puzzle with 0 words")

    word_by_answer: dict[str, Word] = {}
    word_inputs: list[WordInput] = []

    for w in words:
        if w.answer in word_by_answer:
            continue
        word_by_answer[w.answer] = w
        word_inputs.append(WordInput(answer=w.answer, ref=w.id))

    result, grid_strings, quality, win_cfg, win_seed, win_strategy, retry_history = (
        _run_engine_with_optional_retries(
            word_inputs,
            eng_cfg,
            min_density=min_density,
            min_crossings=min_crossings,
            auto_retry=auto_retry,
            max_retries=max_retries,
        )
    )

    retained_map = dict(retained_clues or {})
    unplaced_list = [{"answer": u.answer, "reason": u.reason} for u in result.unplaced]

    puzzle_Entries: list[PuzzleEntry] = []
    missing_clue_count = 0

    for e in result.entries:
        w = word_by_answer.get(e.answer)
        clue_id: Optional[int] = retained_map.get(e.answer)
        if clue_id is None and w is not None:
            active_clue = resolve_clue_for_word(
                w.clues,
                mode=clue_mode,
                difficulty=difficulty,
                preferred_clue_id=preferred_clue_by_answer.get(e.answer),
            )
            if active_clue is not None:
                clue_id = active_clue.id
                retained_map[e.answer] = clue_id
        if clue_id is None:
            missing_clue_count += 1

        puzzle_Entries.append(
            PuzzleEntry(
                word_id=w.id if w else None,
                clue_id=clue_id,
                answer=e.answer,
                display=display_by_answer.get(e.answer) or (w.display if w else e.answer),
                number=e.number or 1,
                direction=e.direction,
                row=e.row,
                col=e.col,
                length=len(e.answer),
            )
        )

    clue_status = "complete" if (missing_clue_count == 0 and len(puzzle_Entries) > 0) else "incomplete"
    persisted_status = "Needs attention" if not quality["meets_threshold"] else result.status

    puzzle = Puzzle(
        collection_id=collection_id,
        title=title or "Crossword Puzzle",
        status=persisted_status,
        clue_status=clue_status,
        rows=result.rows,
        cols=result.cols,
        grid=grid_strings,
        settings={
            "engine": asdict(win_cfg),
            "clue_mode": clue_mode,
            "difficulty": difficulty,
            "retained_clues": retained_map,
            "word_ids": [w.id for w in words],
            "winning_seed": win_seed,
            "winning_strategy": win_strategy,
            "quality": quality,
            "retry_history": retry_history,
        },
        validation=asdict(result.validation),
        unplaced=unplaced_list,
        stats=result.stats,
        entries=puzzle_Entries,
    )
    db.add(puzzle)

    if col_obj is not None:
        meta = dict(col_obj.chapter_meta or {})
        meta["winning_seed"] = win_seed
        meta["winning_strategy"] = win_strategy
        meta["quality"] = quality
        meta["unplaced_words"] = unplaced_list
        meta["hit_time_limit"] = bool((result.stats or {}).get("hit_time_limit"))
        meta["status"] = quality["status"]
        col_obj.chapter_meta = meta

    db.commit()
    db.refresh(puzzle)
    return puzzle


def edit_puzzle_entry_clue(
    db: Session,
    puzzle_id: int,
    entry_id: int,
    new_text: str,
    *,
    difficulty: Optional[str] = None,
) -> dict[str, Any]:
    """Create a manual approved clue and repoint only the target entry without regenerating the grid."""
    puzzle = db.scalar(
        select(Puzzle).where(Puzzle.id == puzzle_id).options(selectinload(Puzzle.entries))
    )
    if puzzle is None:
        raise LookupError(f"Puzzle {puzzle_id} not found")

    entry = next((e for e in puzzle.entries if e.id == entry_id), None)
    if entry is None:
        raise LookupError(f"Entry {entry_id} not found in puzzle {puzzle_id}")

    word_id = entry.word_id
    if word_id is None:
        w = _ensure_word(db, entry.answer)
        word_id = w.id
        entry.word_id = word_id

    eff_diff = difficulty or (puzzle.settings or {}).get("difficulty")
    manual_clue = Clue(
        word_id=word_id,
        text=new_text.strip(),
        difficulty=eff_diff,
        source="manual",
        status="approved",
    )
    db.add(manual_clue)
    db.flush()

    entry.clue_id = manual_clue.id

    # Persist in retained_clues map so future regenerations keep this edited clue
    settings_copy = dict(puzzle.settings or {})
    retained = dict(settings_copy.get("retained_clues") or {})
    retained[entry.answer] = manual_clue.id
    settings_copy["retained_clues"] = retained
    puzzle.settings = settings_copy

    puzzle.clue_status = (
        "complete"
        if all(e.clue_id is not None for e in puzzle.entries) and len(puzzle.entries) > 0
        else "incomplete"
    )
    db.commit()
    db.refresh(puzzle)
    return serialize_puzzle(db, puzzle)


def regenerate_existing_puzzle(
    db: Session,
    puzzle_id: int,
    *,
    add_words: Optional[list[dict[str, Optional[str]]]] = None,
    remove_words: Optional[list[str]] = None,
    replace_words: Optional[list[dict[str, Optional[str]]]] = None,
    engine_overrides: Optional[dict[str, Any]] = None,
    clue_mode: Optional[str] = None,
    difficulty: Optional[str] = None,
    min_density: Optional[float] = None,
    min_crossings: Optional[int] = None,
    auto_retry: bool = False,
    max_retries: int = 3,
) -> Puzzle:
    """Regenerate a puzzle's grid with word or setting changes while preserving clue links for retained words."""
    puzzle = db.scalar(
        select(Puzzle).where(Puzzle.id == puzzle_id).options(selectinload(Puzzle.entries))
    )
    if puzzle is None:
        raise LookupError(f"Puzzle {puzzle_id} not found")

    stored_settings = dict(puzzle.settings or {})
    eff_mode = clue_mode or stored_settings.get("clue_mode", "hybrid")
    eff_diff = difficulty or stored_settings.get("difficulty", "medium")

    # Map retained answers -> clue_id from current entries + stored retained_clues
    retained_clues: dict[str, int] = dict(stored_settings.get("retained_clues") or {})
    for e in puzzle.entries:
        if e.clue_id is not None:
            retained_clues[e.answer] = e.clue_id

    # Reconstruct current word list in order
    word_ids: list[int] = list(stored_settings.get("word_ids") or [])
    current_words: list[Word] = []
    if word_ids:
        loaded = {
            w.id: w
            for w in db.scalars(
                select(Word).where(Word.id.in_(word_ids)).options(selectinload(Word.clues))
            ).all()
        }
        current_words = [loaded[wid] for wid in word_ids if wid in loaded]
    else:
        for e in puzzle.entries:
            if e.word_id:
                w = db.scalar(
                    select(Word).where(Word.id == e.word_id).options(selectinload(Word.clues))
                )
                if w:
                    current_words.append(w)

    # 1. Remove words
    remove_norm: set[str] = set()
    for raw in remove_words or []:
        ans, _ = normalize_answer(raw)
        if ans:
            remove_norm.add(ans)
            retained_clues.pop(ans, None)

    updated_words: list[Word] = [w for w in current_words if w.answer not in remove_norm]

    # 2. Replace words
    for rep in replace_words or []:
        old_ans, _ = normalize_answer(rep.get("old") or "")
        new_raw = rep.get("new") or ""
        new_clue = rep.get("clue")
        if not old_ans or not new_raw:
            continue
        retained_clues.pop(old_ans, None)
        new_word = _ensure_word(db, new_raw, clue_text=new_clue, difficulty=eff_diff)
        if new_clue:
            active = resolve_clue_for_word(new_word.clues, mode="hybrid", difficulty=eff_diff)
            if active:
                retained_clues[new_word.answer] = active.id
        replaced = False
        for idx, w in enumerate(updated_words):
            if w.answer == old_ans:
                updated_words[idx] = new_word
                replaced = True
                break
        if not replaced:
            updated_words.append(new_word)

    # 3. Add words
    existing_ans = {w.answer for w in updated_words}
    for item in add_words or []:
        raw_w = item.get("word") or ""
        clue_t = item.get("clue")
        new_word = _ensure_word(db, raw_w, clue_text=clue_t, difficulty=eff_diff)
        if clue_t:
            active = resolve_clue_for_word(new_word.clues, mode="hybrid", difficulty=eff_diff)
            if active:
                retained_clues[new_word.answer] = active.id
        if new_word.answer not in existing_ans:
            updated_words.append(new_word)
            existing_ans.add(new_word.answer)

    if not updated_words:
        raise ValueError("Cannot regenerate puzzle: word list is empty after modifications")

    # Sync collection words if puzzle belongs to a collection (preserving link metadata)
    col_obj: Optional[Collection] = None
    if puzzle.collection_id is not None:
        col_obj = db.get(Collection, puzzle.collection_id)
        existing_links = list(
            db.scalars(
                select(CollectionWord).where(CollectionWord.collection_id == puzzle.collection_id)
            ).all()
        )
        link_meta_by_wid = {
            lnk.word_id: {
                "display": lnk.display,
                "raw_word": lnk.raw_word,
                "raw_clue": lnk.raw_clue,
                "cell_ref": lnk.cell_ref,
                "extra_data": list(lnk.extra_data or []),
                "clue_id": lnk.clue_id,
            }
            for lnk in existing_links
        }
        db.query(CollectionWord).filter(CollectionWord.collection_id == puzzle.collection_id).delete()
        for pos, w in enumerate(updated_words):
            prev = link_meta_by_wid.get(w.id, {})
            db.add(
                CollectionWord(
                    collection_id=puzzle.collection_id,
                    word_id=w.id,
                    position=pos,
                    display=prev.get("display") or w.display,
                    raw_word=prev.get("raw_word") or w.display,
                    raw_clue=prev.get("raw_clue"),
                    cell_ref=prev.get("cell_ref"),
                    extra_data=prev.get("extra_data") or [],
                    clue_id=prev.get("clue_id") or retained_clues.get(w.answer),
                )
            )
        db.flush()

    # Merge engine settings
    eng_dict = dict(stored_settings.get("engine") or {})
    if engine_overrides:
        for k, v in engine_overrides.items():
            if v is not None and k in EngineSettings.__dataclass_fields__:
                eng_dict[k] = v
    eng_cfg = EngineSettings(**eng_dict)

    stored_quality = stored_settings.get("quality") or {}
    eff_min_density = float(min_density if min_density is not None else stored_quality.get("min_density", 0.15))
    eff_min_crossings = min_crossings if min_crossings is not None else stored_quality.get("min_crossings")

    word_by_answer = {w.answer: w for w in updated_words}
    word_inputs = [WordInput(answer=w.answer, ref=w.id) for w in updated_words]
    result, grid_strings, quality, win_cfg, win_seed, win_strategy, retry_history = (
        _run_engine_with_optional_retries(
            word_inputs,
            eng_cfg,
            min_density=eff_min_density,
            min_crossings=eff_min_crossings,
            auto_retry=auto_retry,
            max_retries=max_retries,
        )
    )

    # Rebuild entries preserving retained_clues
    db.query(PuzzleEntry).filter(PuzzleEntry.puzzle_id == puzzle.id).delete()
    db.flush()

    new_entries: list[PuzzleEntry] = []
    missing_clue_count = 0
    for e in result.entries:
        w = word_by_answer.get(e.answer)
        clue_id = retained_clues.get(e.answer)
        if clue_id is None and w is not None:
            active = resolve_clue_for_word(w.clues, mode=eff_mode, difficulty=eff_diff)
            if active is not None:
                clue_id = active.id
                retained_clues[e.answer] = clue_id
        if clue_id is None:
            missing_clue_count += 1

        pe = PuzzleEntry(
            puzzle_id=puzzle.id,
            word_id=w.id if w else None,
            clue_id=clue_id,
            answer=e.answer,
            display=w.display if w else e.answer,
            number=e.number or 1,
            direction=e.direction,
            row=e.row,
            col=e.col,
            length=len(e.answer),
        )
        db.add(pe)
        new_entries.append(pe)

    unplaced_list = [{"answer": u.answer, "reason": u.reason} for u in result.unplaced]
    puzzle.status = "Needs attention" if not quality["meets_threshold"] else result.status
    puzzle.clue_status = (
        "complete" if (missing_clue_count == 0 and len(new_entries) > 0) else "incomplete"
    )
    puzzle.rows = result.rows
    puzzle.cols = result.cols
    puzzle.grid = grid_strings
    puzzle.unplaced = unplaced_list
    puzzle.validation = asdict(result.validation)
    puzzle.stats = result.stats
    puzzle.settings = {
        "engine": asdict(win_cfg),
        "clue_mode": eff_mode,
        "difficulty": eff_diff,
        "retained_clues": retained_clues,
        "word_ids": [w.id for w in updated_words],
        "winning_seed": win_seed,
        "winning_strategy": win_strategy,
        "quality": quality,
        "retry_history": retry_history,
    }

    if col_obj is not None:
        meta = dict(col_obj.chapter_meta or {})
        meta["winning_seed"] = win_seed
        meta["winning_strategy"] = win_strategy
        meta["quality"] = quality
        meta["unplaced_words"] = unplaced_list
        meta["hit_time_limit"] = bool((result.stats or {}).get("hit_time_limit"))
        meta["status"] = quality["status"]
        col_obj.chapter_meta = meta

    db.commit()
    db.refresh(puzzle)
    return puzzle


def build_puzzle_export_data(
    db: Session,
    puzzle: Puzzle,
    *,
    force: bool = False,
) -> ExportPuzzleData:
    """Validate puzzle and clue completeness, then return ExportPuzzleData."""
    entries = sorted(puzzle.entries, key=lambda e: (e.number, e.direction))
    valid, errors = recheck_puzzle_validity(puzzle, entries)
    if not valid or puzzle.status == "invalid":
        raise ValueError(f"Puzzle failed independent validation and cannot be exported: {errors}")

    clue_ids = [e.clue_id for e in entries if e.clue_id is not None]
    clues_by_id = {
        c.id: c.text
        for c in (
            db.scalars(select(Clue).where(Clue.id.in_(clue_ids))).all() if clue_ids else []
        )
    }

    word_ids = [e.word_id for e in entries if e.word_id is not None]
    words_by_id = {
        w.id: w
        for w in (
            db.scalars(select(Word).where(Word.id.in_(word_ids))).all() if word_ids else []
        )
    }

    missing = [e.answer for e in entries if not e.clue_id or e.clue_id not in clues_by_id]
    if missing and not force:
        raise PermissionError(
            f"Clues incomplete for placed words: {', '.join(missing)}. Supply clues or pass force=true."
        )

    export_entries = [
        ExportEntry(
            number=e.number,
            direction=e.direction,
            row=e.row,
            col=e.col,
            answer=e.answer,
            clue=clues_by_id.get(e.clue_id, "[Missing clue]") if e.clue_id else "[Missing clue]",
            display=e.display or (words_by_id[e.word_id].display if e.word_id in words_by_id else e.answer),
        )
        for e in entries
    ]
    return ExportPuzzleData(
        title=puzzle.title,
        rows=puzzle.rows,
        cols=puzzle.cols,
        grid=list(puzzle.grid),
        entries=export_entries,
    )


def render_stored_puzzle_export(
    db: Session,
    puzzle_id: int,
    *,
    kind: str = "puzzle",
    fmt: str = "svg",
    page: int = 0,
    force: bool = False,
    settings: Optional[ExportSettings] = None,
    title_override: Optional[str] = None,
    solution_title_override: Optional[str] = None,
) -> tuple[bytes | str, str]:
    puzzle = db.scalar(
        select(Puzzle).where(Puzzle.id == puzzle_id).options(selectinload(Puzzle.entries))
    )
    if puzzle is None:
        raise LookupError(f"Puzzle {puzzle_id} not found")

    exp_data = build_puzzle_export_data(db, puzzle, force=force)
    if title_override is not None or solution_title_override is not None:
        exp_data = ExportPuzzleData(
            title=title_override if title_override is not None else exp_data.title,
            solution_title=solution_title_override,
            rows=exp_data.rows,
            cols=exp_data.cols,
            grid=exp_data.grid,
            entries=exp_data.entries,
        )
    exp_settings = settings or ExportSettings()
    font_dir = get_settings().font_dir
    pages = build_export_pages(exp_data, kind, exp_settings, font_dir=font_dir)

    if fmt == "pdf":
        return render_pdf(pages, font_dir=font_dir), "application/pdf"
    if page >= len(pages):
        raise ValueError(f"Page {page} out of range (total {len(pages)})")
    if fmt == "svg":
        return render_svg(pages[page]), "image/svg+xml"
    return render_png(pages[page], dpi=exp_settings.dpi, font_dir=font_dir), "image/png"
