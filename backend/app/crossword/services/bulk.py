"""Bulk puzzle generation with ProcessPoolExecutor, reproducible auto-retry, failure isolation, ZIP and book PDF export."""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings, redact_secrets
from ..engine import EngineSettings, WordInput, generate_crossword
from ..models import Collection, Job, Puzzle, PuzzleEntry, Word
from .clues.ai import AIProvider
from .clues.dictionary import DictionaryProvider
from .clues.service import (
    create_clue_generation_job,
    execute_clue_generation_job,
    resolve_clue_for_word,
)
from .export.geometry import build_export_pages
from .export.primitives import PagePrimitives
from .export.renderers import render_pdf, render_png, render_svg
from .export.settings import ExportSettings
from .puzzles import build_puzzle_export_data
from .quality import (
    build_plain_language_diagnostics,
    build_retry_schedule,
    compute_grid_quality_metrics,
    evaluate_quality_threshold,
)


def _run_engine_worker(answers: list[str], settings_dict: dict[str, Any]) -> dict[str, Any]:
    """Top-level picklable worker function for ProcessPoolExecutor."""
    cfg = EngineSettings(**settings_dict)
    inputs = [WordInput(answer=a, ref=a) for a in answers]
    res = generate_crossword(inputs, cfg)
    entries_out = [
        {
            "answer": e.answer,
            "row": e.row,
            "col": e.col,
            "direction": e.direction,
            "number": e.number or 1,
        }
        for e in res.entries
    ]
    unplaced_out = [{"answer": u.answer, "reason": u.reason} for u in res.unplaced]
    metrics = compute_grid_quality_metrics(res.cells, entries_out, unplaced_out)
    return {
        "status": res.status,
        "rows": res.rows,
        "cols": res.cols,
        "cells": res.cells,
        "entries": entries_out,
        "unplaced": unplaced_out,
        "validation": asdict(res.validation),
        "stats": res.stats,
        "metrics": metrics,
    }


def _candidate_rank_key(res_dict: dict[str, Any], quality: dict[str, Any]) -> tuple:
    val_ok = 1 if (res_dict.get("validation") or {}).get("valid") and res_dict.get("entries") else 0
    meets = 1 if quality.get("meets_threshold") else 0
    placed = int(quality.get("placed_count", 0))
    unplaced = int(quality.get("unplaced_count", 0))
    density = float(quality.get("density", 0.0))
    crossings = int(quality.get("crossing_count", 0))
    area = int(quality.get("total_cells", 0))
    return (val_ok, meets, placed, -unplaced, round(density, 4), crossings, -area)


def _run_chapter_with_retries(
    answers: list[str],
    settings_dict: dict[str, Any],
    min_density: float = 0.15,
    min_crossings: Optional[int] = None,
    auto_retry: bool = True,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Run engine across bounded deterministic (seed, strategy) retries and keep the best result."""
    base_seed = int(settings_dict.get("seed", 0))
    base_strategy = str(settings_dict.get("strategy", "auto") or "auto")
    schedule = build_retry_schedule(
        base_seed=base_seed,
        base_strategy=base_strategy,
        max_retries=max_retries if auto_retry else 0,
    )

    best_bundle: Optional[tuple[tuple, dict[str, Any], dict[str, Any], int, str]] = None
    retry_history: list[dict[str, Any]] = []
    any_hit_time_limit = False

    for try_seed, try_strategy in schedule:
        cand_cfg = dict(settings_dict)
        cand_cfg["seed"] = try_seed
        cand_cfg["strategy"] = try_strategy

        res_dict = _run_engine_worker(answers, cand_cfg)
        metrics = res_dict.get("metrics") or compute_grid_quality_metrics(
            res_dict.get("cells") or [],
            res_dict.get("entries") or [],
            res_dict.get("unplaced") or [],
        )
        val_valid = bool((res_dict.get("validation") or {}).get("valid"))
        quality = evaluate_quality_threshold(
            metrics,
            validation_valid=val_valid,
            min_density=min_density,
            min_crossings=min_crossings,
        )
        hit_tl = bool((res_dict.get("stats") or {}).get("hit_time_limit"))
        if hit_tl:
            any_hit_time_limit = True

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

        rank = _candidate_rank_key(res_dict, quality)
        if best_bundle is None or rank > best_bundle[0]:
            best_bundle = (rank, res_dict, quality, try_seed, try_strategy)

        if quality["meets_threshold"]:
            break

    assert best_bundle is not None
    _, best_res, best_quality, win_seed, win_strategy = best_bundle
    if any_hit_time_limit:
        best_res.setdefault("stats", {})["hit_time_limit"] = True

    return {
        "result": best_res,
        "quality": best_quality,
        "winning_seed": win_seed,
        "winning_strategy": win_strategy,
        "attempts_tried": len(retry_history),
        "retry_history": retry_history,
        "hit_time_limit": bool((best_res.get("stats") or {}).get("hit_time_limit")),
    }


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "puzzle").strip()).strip("_").lower()
    return s or "puzzle"


def _build_slices(
    collections: list[Collection],
    max_words_per_puzzle: Optional[int],
) -> list[dict[str, Any]]:
    slices: list[dict[str, Any]] = []
    for col in collections:
        word_ids = [link.word_id for link in col.word_links]
        if not word_ids:
            slices.append({"collection_id": col.id, "title": col.name, "word_ids": []})
            continue
        if max_words_per_puzzle and max_words_per_puzzle > 0 and len(word_ids) > max_words_per_puzzle:
            chunks = [
                word_ids[i : i + max_words_per_puzzle]
                for i in range(0, len(word_ids), max_words_per_puzzle)
            ]
            for idx, chunk in enumerate(chunks, start=1):
                slices.append(
                    {
                        "collection_id": col.id,
                        "title": f"{col.name} (Part {idx})",
                        "word_ids": chunk,
                    }
                )
        else:
            slices.append({"collection_id": col.id, "title": col.name, "word_ids": word_ids})
    return slices


def create_bulk_generation_job(
    db: Session,
    *,
    collection_ids: list[int],
    engine_settings: Optional[EngineSettings] = None,
    clue_mode: str = "hybrid",
    difficulty: str = "medium",
    generate_missing_clues: bool = True,
    max_words_per_puzzle: Optional[int] = None,
    max_workers: int = 2,
    min_density: float = 0.15,
    min_crossings: Optional[int] = None,
    auto_retry: bool = True,
    max_retries: int = 3,
) -> Job:
    cols = list(
        db.scalars(
            select(Collection)
            .where(Collection.id.in_(collection_ids))
            .options(selectinload(Collection.word_links))
        ).all()
    )
    col_by_id = {c.id: c for c in cols}
    ordered_cols = [col_by_id[cid] for cid in collection_ids if cid in col_by_id]
    if not ordered_cols:
        raise LookupError("No matching collections found")

    slices = _build_slices(ordered_cols, max_words_per_puzzle)
    eng_cfg = engine_settings or EngineSettings()

    job = Job(
        id=uuid.uuid4().hex,
        type="bulk_puzzle_generation",
        status="pending",
        total=len(slices),
        completed=0,
        failed=0,
        payload={
            "collection_ids": collection_ids,
            "slices": slices,
            "engine": asdict(eng_cfg),
            "clue_mode": clue_mode,
            "difficulty": difficulty,
            "generate_missing_clues": generate_missing_clues,
            "max_words_per_puzzle": max_words_per_puzzle,
            "max_workers": max_workers,
            "min_density": min_density,
            "min_crossings": min_crossings,
            "auto_retry": auto_retry,
            "max_retries": max_retries,
        },
        result={
            "puzzles": [],
            "failures": [],
            "needs_attention": [],
            "hit_time_limit": False,
            "time_limit_warnings": [],
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def execute_bulk_generation_job(
    job_id: str,
    session_factory: Callable[[], Session],
    *,
    dictionary_provider: Optional[DictionaryProvider] = None,
    ai_provider: Optional[AIProvider] = None,
    use_process_pool: bool = True,
) -> None:
    """Execute bulk clue pre-generation + isolated per-puzzle generation with reproducible retries."""
    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
            job.status = "cancelled"
            db.commit()
            return
        payload = dict(job.payload or {})
        slices: list[dict[str, Any]] = payload.get("slices", [])
        eng_dict: dict[str, Any] = payload.get("engine", {})
        clue_mode: str = payload.get("clue_mode", "hybrid")
        difficulty: str = payload.get("difficulty", "medium")
        gen_clues: bool = bool(payload.get("generate_missing_clues", True))
        max_workers: int = int(payload.get("max_workers", 2))
        min_density: float = float(payload.get("min_density", 0.15))
        min_crossings: Optional[int] = payload.get("min_crossings")
        auto_retry: bool = bool(payload.get("auto_retry", True))
        max_retries: int = int(payload.get("max_retries", 3))

        job.status = "running"
        db.commit()

        try:
            # 1. Generate missing clues automatically first if requested
            all_word_ids = sorted({wid for s in slices for wid in s.get("word_ids", [])})
            if gen_clues and all_word_ids and clue_mode in ("hybrid", "automatic"):
                clue_job = create_clue_generation_job(
                    db,
                    word_ids=all_word_ids,
                    mode=clue_mode,
                    difficulty=difficulty,
                )
                execute_clue_generation_job(
                    clue_job.id,
                    session_factory,
                    dictionary_provider=dictionary_provider,
                    ai_provider=ai_provider,
                )
                db.expire_all()

            # Load words + clues + collections
            words = list(
                db.scalars(
                    select(Word).where(Word.id.in_(all_word_ids)).options(selectinload(Word.clues))
                ).all()
            ) if all_word_ids else []
            word_by_id = {w.id: w for w in words}

            col_ids = sorted({s.get("collection_id") for s in slices if s.get("collection_id") is not None})
            col_by_id = {
                c.id: c
                for c in (
                    db.scalars(select(Collection).where(Collection.id.in_(col_ids))).all()
                    if col_ids
                    else []
                )
            }

            puzzles_created: list[dict[str, Any]] = []
            failures: list[dict[str, Any]] = []
            needs_attention_list: list[dict[str, Any]] = []
            time_limit_warnings: list[dict[str, Any]] = []

            pool: Optional[ProcessPoolExecutor] = None
            if use_process_pool and max_workers > 1 and len(slices) > 1:
                try:
                    pool = ProcessPoolExecutor(max_workers=max_workers)
                except Exception:
                    pool = None

            try:
                futures: list[tuple[dict[str, Any], list[Word], Any]] = []
                for sl in slices:
                    db.refresh(job)
                    if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                        for _, _, pending_fut in futures:
                            if pending_fut is not None:
                                pending_fut.cancel()
                        job.status = "cancelled"
                        db.commit()
                        return
                    sl_words = [word_by_id[wid] for wid in sl.get("word_ids", []) if wid in word_by_id]
                    if not sl_words:
                        failures.append(
                            {
                                "collection_id": sl.get("collection_id"),
                                "title": sl.get("title"),
                                "reason": "collection has no valid words",
                            }
                        )
                        job.failed += 1
                        db.commit()
                        continue

                    answers = [w.answer for w in sl_words]
                    if pool is not None:
                        fut = pool.submit(
                            _run_chapter_with_retries,
                            answers,
                            eng_dict,
                            min_density,
                            min_crossings,
                            auto_retry,
                            max_retries,
                        )
                        futures.append((sl, sl_words, fut))
                    else:
                        futures.append((sl, sl_words, None))

                for sl, sl_words, fut in futures:
                    db.refresh(job)
                    if job.status == "cancelled" or (job.payload or {}).get("cancel_requested"):
                        for _, _, rem_fut in futures:
                            if rem_fut is not None:
                                rem_fut.cancel()
                        job.status = "cancelled"
                        db.commit()
                        return
                    try:
                        if fut is not None:
                            bundle = fut.result()
                        else:
                            bundle = _run_chapter_with_retries(
                                [w.answer for w in sl_words],
                                eng_dict,
                                min_density=min_density,
                                min_crossings=min_crossings,
                                auto_retry=auto_retry,
                                max_retries=max_retries,
                            )

                        res_dict = bundle["result"]
                        quality = bundle["quality"]
                        win_seed = bundle["winning_seed"]
                        win_strategy = bundle["winning_strategy"]
                        attempts_tried = bundle["attempts_tried"]
                        retry_history = bundle["retry_history"]
                        hit_tl = bundle["hit_time_limit"]

                        status = res_dict["status"]
                        val = res_dict["validation"]
                        if status in ("invalid", "empty") or not val.get("valid") or not res_dict["entries"]:
                            raise ValueError(
                                f"Engine returned status='{status}', errors={val.get('errors')}"
                            )

                        word_by_ans = {w.answer: w for w in sl_words}
                        entries_models: list[PuzzleEntry] = []
                        retained_map: dict[str, int] = {}
                        missing_clues = 0
                        missing_clue_words: list[str] = []

                        for e in res_dict["entries"]:
                            w = word_by_ans.get(e["answer"])
                            clue_id: Optional[int] = None
                            if w is not None:
                                active = resolve_clue_for_word(
                                    w.clues, mode=clue_mode, difficulty=difficulty
                                )
                                if active is not None:
                                    clue_id = active.id
                                    retained_map[e["answer"]] = clue_id
                            if clue_id is None:
                                missing_clues += 1
                                missing_clue_words.append(e["answer"])

                            entries_models.append(
                                PuzzleEntry(
                                    word_id=w.id if w else None,
                                    clue_id=clue_id,
                                    answer=e["answer"],
                                    display=w.display if w else e["answer"],
                                    number=e["number"],
                                    direction=e["direction"],
                                    row=e["row"],
                                    col=e["col"],
                                    length=len(e["answer"]),
                                )
                            )

                        clue_status = (
                            "complete"
                            if (missing_clues == 0 and len(entries_models) > 0)
                            else "incomplete"
                        )
                        grid_strings = ["".join(c or "#" for c in row) for row in res_dict["cells"]]

                        diagnostics = build_plain_language_diagnostics(
                            validation=val,
                            unplaced=res_dict["unplaced"],
                            quality=quality,
                            stats=res_dict["stats"],
                            missing_clues=missing_clue_words if clue_status == "incomplete" else None,
                        )
                        needs_attention = not quality["meets_threshold"]
                        persisted_status = "Needs attention" if needs_attention else status

                        stored_eng = dict(eng_dict)
                        stored_eng["seed"] = win_seed
                        stored_eng["strategy"] = win_strategy

                        puzzle = Puzzle(
                            collection_id=sl.get("collection_id"),
                            title=sl.get("title") or "Crossword Puzzle",
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
                                "word_ids": [w.id for w in sl_words],
                                "winning_seed": win_seed,
                                "winning_strategy": win_strategy,
                                "quality": quality,
                                "retry_history": retry_history,
                            },
                            validation=val,
                            unplaced=res_dict["unplaced"],
                            stats=res_dict["stats"],
                            entries=entries_models,
                        )
                        db.add(puzzle)
                        db.flush()

                        col_obj = col_by_id.get(sl.get("collection_id"))
                        if col_obj is not None:
                            meta = dict(col_obj.chapter_meta or {})
                            meta["winning_seed"] = win_seed
                            meta["winning_strategy"] = win_strategy
                            meta["quality"] = quality
                            meta["unplaced_words"] = res_dict["unplaced"]
                            meta["hit_time_limit"] = hit_tl
                            meta["status"] = quality["status"]
                            col_obj.chapter_meta = meta

                        summary_item = {
                            "puzzle_id": puzzle.id,
                            "collection_id": puzzle.collection_id,
                            "title": puzzle.title,
                            "status": persisted_status,
                            "quality_status": quality["status"],
                            "needs_attention": needs_attention,
                            "clue_status": puzzle.clue_status,
                            "placed_count": len(entries_models),
                            "unplaced_count": len(res_dict["unplaced"]),
                            "unplaced": res_dict["unplaced"],
                            "winning_seed": win_seed,
                            "winning_strategy": win_strategy,
                            "attempts_tried": attempts_tried,
                            "retry_history": retry_history,
                            "hit_time_limit": hit_tl,
                            "quality": quality,
                            "diagnostics": diagnostics,
                            "plain_errors": diagnostics["messages"],
                        }
                        puzzles_created.append(summary_item)
                        if needs_attention:
                            needs_attention_list.append(summary_item)
                        if hit_tl:
                            time_limit_warnings.append(
                                {
                                    "puzzle_id": puzzle.id,
                                    "collection_id": puzzle.collection_id,
                                    "title": puzzle.title,
                                    "message": "Search hit the safety time limit; layout may not be reproducible.",
                                }
                            )
                        job.completed += 1
                    except Exception as exc:
                        failures.append(
                            {
                                "collection_id": sl.get("collection_id"),
                                "title": sl.get("title"),
                                "reason": redact_secrets(str(exc)),
                            }
                        )
                        job.failed += 1

                    job.result = {
                        "puzzles": puzzles_created,
                        "failures": failures,
                        "needs_attention": needs_attention_list,
                        "hit_time_limit": len(time_limit_warnings) > 0,
                        "time_limit_warnings": time_limit_warnings,
                    }
                    db.commit()
            finally:
                if pool is not None:
                    pool.shutdown(wait=True)

            job.status = "completed"
            job.result = {
                "puzzles": puzzles_created,
                "failures": failures,
                "needs_attention": needs_attention_list,
                "hit_time_limit": len(time_limit_warnings) > 0,
                "time_limit_warnings": time_limit_warnings,
            }
            db.commit()
        except Exception as exc:
            job.status = "failed"
            job.error = redact_secrets(str(exc))
            db.commit()


def _resolve_bulk_puzzles(
    db: Session,
    *,
    puzzle_ids: Optional[list[int]] = None,
    job_id: Optional[str] = None,
) -> list[Puzzle]:
    target_ids: list[int] = list(puzzle_ids or [])
    if not target_ids and job_id:
        job = db.get(Job, job_id)
        if job is None:
            raise LookupError(f"Job {job_id} not found")
        target_ids = [
            p["puzzle_id"]
            for p in (job.result or {}).get("puzzles", [])
            if isinstance(p, dict) and p.get("puzzle_id")
        ]

    if not target_ids:
        raise ValueError("No puzzles specified for bulk export")

    loaded = {
        p.id: p
        for p in db.scalars(
            select(Puzzle).where(Puzzle.id.in_(target_ids)).options(selectinload(Puzzle.entries))
        ).all()
    }
    ordered = [loaded[pid] for pid in target_ids if pid in loaded]
    if not ordered:
        raise LookupError("None of the requested puzzles were found")
    return ordered


def build_bulk_zip(
    db: Session,
    *,
    puzzle_ids: Optional[list[int]] = None,
    job_id: Optional[str] = None,
    kinds: list[str] | None = None,
    formats: list[str] | None = None,
    force: bool = False,
    settings: Optional[ExportSettings] = None,
) -> bytes:
    puzzles = _resolve_bulk_puzzles(db, puzzle_ids=puzzle_ids, job_id=job_id)
    exp_kinds = kinds or ["puzzle", "clues", "answer_key"]
    exp_formats = formats or ["svg", "pdf"]
    exp_settings = settings or ExportSettings()
    font_dir = get_settings().font_dir

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, puzzle in enumerate(puzzles, start=1):
            exp_data = build_puzzle_export_data(db, puzzle, force=force)
            folder = f"{idx:03d}_{_slugify(puzzle.title)}"
            for kind in exp_kinds:
                pages = build_export_pages(exp_data, kind, exp_settings, font_dir=font_dir)
                for fmt in exp_formats:
                    if fmt == "pdf":
                        zf.writestr(f"{folder}/{kind}.pdf", render_pdf(pages, font_dir=font_dir))
                    elif fmt == "svg":
                        if len(pages) == 1:
                            zf.writestr(f"{folder}/{kind}.svg", render_svg(pages[0]))
                        else:
                            for p_idx, page in enumerate(pages, start=1):
                                zf.writestr(f"{folder}/{kind}_p{p_idx}.svg", render_svg(page))
                    elif fmt == "png":
                        if len(pages) == 1:
                            zf.writestr(
                                f"{folder}/{kind}.png",
                                render_png(pages[0], dpi=exp_settings.dpi, font_dir=font_dir),
                            )
                        else:
                            for p_idx, page in enumerate(pages, start=1):
                                zf.writestr(
                                    f"{folder}/{kind}_p{p_idx}.png",
                                    render_png(page, dpi=exp_settings.dpi, font_dir=font_dir),
                                )
    return buf.getvalue()


def build_combined_book_pdf(
    db: Session,
    *,
    puzzle_ids: Optional[list[int]] = None,
    job_id: Optional[str] = None,
    include_separate_clue_pages: bool = False,
    force: bool = False,
    settings: Optional[ExportSettings] = None,
) -> bytes:
    """Build one combined book PDF with all puzzles/clues first and all answer keys at the end."""
    puzzles = _resolve_bulk_puzzles(db, puzzle_ids=puzzle_ids, job_id=job_id)
    exp_settings = settings or ExportSettings()
    font_dir = get_settings().font_dir

    front_pages: list[PagePrimitives] = []
    back_answer_pages: list[PagePrimitives] = []

    for puzzle in puzzles:
        exp_data = build_puzzle_export_data(db, puzzle, force=force)
        if include_separate_clue_pages:
            front_pages.extend(build_export_pages(exp_data, "puzzle", exp_settings, font_dir=font_dir))
            front_pages.extend(build_export_pages(exp_data, "clues", exp_settings, font_dir=font_dir))
        else:
            front_pages.extend(
                build_export_pages(exp_data, "puzzle_with_clues", exp_settings, font_dir=font_dir)
            )
        back_answer_pages.extend(
            build_export_pages(exp_data, "answer_key", exp_settings, font_dir=font_dir)
        )

    return render_pdf(front_pages + back_answer_pages, font_dir=font_dir)
