"""Import staging and commit API endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ImportBatch
from ..schemas import CommitImportIn, PasteImportIn
from ..services.importer import commit_import, stage_import

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _batch_response(batch: ImportBatch) -> dict:
    return {
        "id": batch.id,
        "filename": batch.filename,
        "source_format": batch.source_format,
        "status": batch.status,
        "report": batch.report,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


@router.post("")
async def create_import(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    collection_name: Optional[str] = Form(None),
    language: str = Form("en"),
    min_word_length: int = Form(3),
    max_word_length: int = Form(30),
    expected_words_per_chapter: Optional[int] = Form(None),
    grid_rows: Optional[int] = Form(None),
    grid_cols: Optional[int] = Form(None),
    max_grid_size: int = Form(40),
    db: Session = Depends(get_db),
):
    if file is None and (text is None or not text.strip()):
        raise HTTPException(status_code=400, detail="Provide either a file upload or non-empty text")

    content_bytes = await file.read() if file is not None else None
    filename = file.filename if file is not None else None

    try:
        batch = stage_import(
            db,
            content_bytes=content_bytes,
            text=text,
            filename=filename,
            collection_name=collection_name,
            language=language,
            min_word_length=min_word_length,
            max_word_length=max_word_length,
            expected_words_per_chapter=expected_words_per_chapter,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            max_grid_size=max_grid_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _batch_response(batch)


@router.post("/paste")
def create_paste_import(body: PasteImportIn, db: Session = Depends(get_db)):
    batch = stage_import(
        db,
        text=body.text,
        collection_name=body.collection_name,
        language=body.language,
        min_word_length=body.min_word_length,
        max_word_length=body.max_word_length,
        expected_words_per_chapter=body.expected_words_per_chapter,
        grid_rows=body.grid_rows,
        grid_cols=body.grid_cols,
        max_grid_size=body.max_grid_size,
    )
    return _batch_response(batch)


@router.get("/{batch_id}")
def get_import(batch_id: str, db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return _batch_response(batch)


@router.post("/{batch_id}/commit")
def commit_import_batch(
    batch_id: str,
    body: Optional[CommitImportIn] = None,
    db: Session = Depends(get_db),
):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    try:
        return commit_import(
            db,
            batch,
            target_collection_id=body.collection_id if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

