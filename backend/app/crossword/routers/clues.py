"""Clue generation, review, editing, alternatives/history, and completeness endpoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, get_session_factory
from ..models import Clue, CollectionWord, Word, utcnow
from ..schemas import (
    BulkApproveCluesIn,
    ClueCreateIn,
    ClueGenerateIn,
    ClueUpdateIn,
    WordClueRegenerateIn,
    WordClueSelectIn,
)
from ..services.clues.service import (
    create_clue_generation_job,
    execute_clue_generation_job,
    get_collection_clues_summary,
    regenerate_word_clue_alternatives,
    select_or_restore_word_clue,
)
from ..services.clues.validator import validate_clue

router = APIRouter(prefix="/api", tags=["clues"])


def _clue_dict(c: Clue) -> dict:
    return {
        "id": c.id,
        "word_id": c.word_id,
        "text": c.text,
        "difficulty": c.difficulty,
        "source": c.source,
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.post("/clues/generate")
def generate_clues(
    body: ClueGenerateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    if body.collection_id is None and not body.word_ids:
        raise HTTPException(status_code=400, detail="Provide collection_id or word_ids")

    try:
        job = create_clue_generation_job(
            db,
            collection_id=body.collection_id,
            word_ids=body.word_ids,
            mode=body.mode,
            difficulty=body.difficulty,
            regenerate=body.regenerate,
            verify=body.verify,
            age_group=body.age_group,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    background_tasks.add_task(execute_clue_generation_job, job.id, session_factory)
    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "total": job.total,
    }


@router.get("/collections/{collection_id}/clues")
def list_collection_clues(
    collection_id: int,
    mode: str = Query("hybrid", pattern="^(automatic|manual|hybrid)$"),
    difficulty: str = Query("medium", pattern="^(easy|medium|hard)$"),
    capitalization: str = Query("sentence"),
    ending_punctuation: str = Query("keep"),
    show_length_hint: bool = Query(True),
    enumeration_display: str = Query("formatted"),
    db: Session = Depends(get_db),
):
    try:
        return get_collection_clues_summary(
            db,
            collection_id,
            mode=mode,
            difficulty=difficulty,
            capitalization=capitalization,
            ending_punctuation=ending_punctuation,
            show_length_hint=show_length_hint,
            enumeration_display=enumeration_display,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/words/{word_id}/clues", status_code=201)
def create_manual_clue(word_id: int, body: ClueCreateIn, db: Session = Depends(get_db)):
    word = db.get(Word, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="Word not found")

    validation = validate_clue(body.text, word.answer)
    clue = Clue(
        word_id=word.id,
        text=body.text.strip(),
        difficulty=body.difficulty,
        source="manual",
        status=body.status,
    )
    db.add(clue)
    db.flush()

    for lnk in db.scalars(select(CollectionWord).where(CollectionWord.word_id == word.id)).all():
        lnk.clue_id = clue.id

    db.commit()
    db.refresh(clue)
    out = _clue_dict(clue)
    out["validation"] = {"valid": validation.valid, "reasons": validation.reasons}
    return out


@router.post("/words/{word_id}/clues/regenerate")
def regenerate_single_word_clue(
    word_id: int,
    body: WordClueRegenerateIn,
    db: Session = Depends(get_db),
):
    try:
        return regenerate_word_clue_alternatives(
            db,
            word_id,
            difficulty=body.difficulty,
            count=body.count,
            verify=body.verify,
            age_group=body.age_group,
            mode=body.mode,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/words/{word_id}/clues/select")
def select_word_clue_alternative(
    word_id: int,
    body: WordClueSelectIn,
    db: Session = Depends(get_db),
):
    try:
        return select_or_restore_word_clue(db, word_id, body.clue_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/words/{word_id}/clues/{clue_id}/restore")
def restore_word_clue(
    word_id: int,
    clue_id: int,
    db: Session = Depends(get_db),
):
    try:
        return select_or_restore_word_clue(db, word_id, clue_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/clues/{clue_id}")
def update_clue(clue_id: int, body: ClueUpdateIn, db: Session = Depends(get_db)):
    clue = db.get(Clue, clue_id)
    if clue is None:
        raise HTTPException(status_code=404, detail="Clue not found")

    # Never overwrite or delete manual/imported clue text; preserve original in history
    if clue.source in ("import", "manual") and body.text is not None and body.text.strip() != clue.text:
        new_clue = Clue(
            word_id=clue.word_id,
            text=body.text.strip(),
            difficulty=body.difficulty or clue.difficulty,
            source="manual",
            status=body.status or "approved",
            updated_at=utcnow(),
        )
        db.add(new_clue)
        db.flush()
        for lnk in db.scalars(select(CollectionWord).where(CollectionWord.clue_id == clue.id)).all():
            lnk.clue_id = new_clue.id
        db.commit()
        db.refresh(new_clue)
        return _clue_dict(new_clue)

    if body.text is not None:
        clue.text = body.text.strip()
    if body.difficulty is not None:
        clue.difficulty = body.difficulty
    if body.status is not None:
        clue.status = body.status
    clue.updated_at = utcnow()

    db.commit()
    db.refresh(clue)
    return _clue_dict(clue)


@router.post("/clues/bulk-approve")
def bulk_approve_clues(body: BulkApproveCluesIn, db: Session = Depends(get_db)):
    if not body.clue_ids and body.collection_id is None:
        raise HTTPException(status_code=400, detail="Provide clue_ids or collection_id")

    if body.clue_ids:
        clues = list(db.scalars(select(Clue).where(Clue.id.in_(body.clue_ids))).all())
    else:
        word_ids = list(
            db.scalars(
                select(CollectionWord.word_id).where(
                    CollectionWord.collection_id == body.collection_id
                )
            ).all()
        )
        clues = list(
            db.scalars(
                select(Clue).where(
                    Clue.word_id.in_(word_ids),
                    Clue.status.in_(["needs_review", "draft"]),
                )
            ).all()
        )

    approved_count = 0
    for c in clues:
        if c.status != "approved":
            c.status = "approved"
            approved_count += 1
    db.commit()
    return {"approved_count": approved_count}
