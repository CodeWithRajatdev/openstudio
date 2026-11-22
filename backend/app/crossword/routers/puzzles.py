"""Persistent puzzle endpoints: generate, inspect, edit clue, regenerate, export."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..engine import EngineSettings
from ..models import Puzzle
from ..schemas import (
    PuzzleEntryClueEditIn,
    PuzzleExportIn,
    PuzzleGenerateIn,
    PuzzleRegenerateIn,
)
from ..services.export.settings import ExportSettings
from ..services.puzzles import (
    edit_puzzle_entry_clue,
    generate_and_save_puzzle,
    regenerate_existing_puzzle,
    render_stored_puzzle_export,
    serialize_puzzle,
)

router = APIRouter(prefix="/api/puzzles", tags=["puzzles"])


@router.get("")
def list_puzzles(db: Session = Depends(get_db)):
    puzzles = list(
        db.scalars(
            select(Puzzle).order_by(Puzzle.id.desc()).options(selectinload(Puzzle.entries))
        ).all()
    )
    return [
        {
            "id": p.id,
            "collection_id": p.collection_id,
            "title": p.title,
            "status": p.status,
            "clue_status": p.clue_status,
            "rows": p.rows,
            "cols": p.cols,
            "entry_count": len(p.entries),
            "unplaced_count": len(p.unplaced or []),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in puzzles
    ]


@router.post("/generate", status_code=201)
def create_puzzle(body: PuzzleGenerateIn, db: Session = Depends(get_db)):
    eng_settings = EngineSettings(**body.settings.model_dump())
    try:
        puzzle = generate_and_save_puzzle(
            db,
            collection_id=body.collection_id,
            title=body.title,
            engine_settings=eng_settings,
            clue_mode=body.clue_mode,
            difficulty=body.difficulty,
            min_density=body.min_density,
            min_crossings=body.min_crossings,
            auto_retry=body.auto_retry,
            max_retries=body.max_retries,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_puzzle(db, puzzle)


@router.get("/{puzzle_id}")
def get_puzzle(
    puzzle_id: int,
    enumeration_display: Optional[str] = Query(None, pattern="^(formatted|total|none)$"),
    db: Session = Depends(get_db),
):
    puzzle = db.scalar(
        select(Puzzle).where(Puzzle.id == puzzle_id).options(selectinload(Puzzle.entries))
    )
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    return serialize_puzzle(db, puzzle, enumeration_display=enumeration_display)


@router.delete("/{puzzle_id}", status_code=204)
def delete_puzzle(puzzle_id: int, db: Session = Depends(get_db)):
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    db.delete(puzzle)
    db.commit()


@router.patch("/{puzzle_id}/entries/{entry_id}/clue")
def update_entry_clue(
    puzzle_id: int,
    entry_id: int,
    body: PuzzleEntryClueEditIn,
    db: Session = Depends(get_db),
):
    try:
        return edit_puzzle_entry_clue(
            db,
            puzzle_id,
            entry_id,
            body.text,
            difficulty=body.difficulty,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{puzzle_id}/regenerate")
def regenerate_puzzle(
    puzzle_id: int,
    body: PuzzleRegenerateIn,
    db: Session = Depends(get_db),
):
    try:
        puzzle = regenerate_existing_puzzle(
            db,
            puzzle_id,
            add_words=[w.model_dump() for w in body.add_words] if body.add_words else None,
            remove_words=body.remove_words,
            replace_words=[w.model_dump() for w in body.replace_words] if body.replace_words else None,
            engine_overrides=body.settings.model_dump() if body.settings else None,
            clue_mode=body.clue_mode,
            difficulty=body.difficulty,
            min_density=body.min_density,
            min_crossings=body.min_crossings,
            auto_retry=body.auto_retry,
            max_retries=body.max_retries,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_puzzle(db, puzzle)


@router.get("/{puzzle_id}/export")
def export_puzzle_get(
    puzzle_id: int,
    kind: str = Query("puzzle", pattern="^(puzzle|clues|answer_key|puzzle_with_clues)$"),
    format: str = Query("svg", pattern="^(svg|pdf|png)$"),
    page: int = Query(0, ge=0),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        content, media_type = render_stored_puzzle_export(
            db, puzzle_id, kind=kind, fmt=format, page=page, force=force
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type=media_type)


@router.post("/{puzzle_id}/export")
def export_puzzle_post(
    puzzle_id: int,
    body: PuzzleExportIn,
    db: Session = Depends(get_db),
):
    settings = ExportSettings(**body.settings.model_dump())
    try:
        content, media_type = render_stored_puzzle_export(
            db,
            puzzle_id,
            kind=body.kind,
            fmt=body.format,
            page=body.page,
            force=body.force,
            settings=settings,
            title_override=body.title_override,
            solution_title_override=body.solution_title_override,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=content, media_type=media_type)
