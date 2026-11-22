"""Bulk puzzle generation and bulk ZIP / combined book PDF export endpoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db, get_session_factory
from ..engine import EngineSettings
from ..schemas import BulkBookPdfExportIn, BulkGenerateIn, BulkZipExportIn
from ..services.bulk import (
    build_bulk_zip,
    build_combined_book_pdf,
    create_bulk_generation_job,
    execute_bulk_generation_job,
)
from ..services.export.settings import ExportSettings

router = APIRouter(prefix="/api/bulk", tags=["bulk"])


@router.post("/generate")
def start_bulk_generation(
    body: BulkGenerateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    eng_settings = EngineSettings(**body.settings.model_dump())
    try:
        job = create_bulk_generation_job(
            db,
            collection_ids=body.collection_ids,
            engine_settings=eng_settings,
            clue_mode=body.clue_mode,
            difficulty=body.difficulty,
            generate_missing_clues=body.generate_missing_clues,
            max_words_per_puzzle=body.max_words_per_puzzle,
            max_workers=body.max_workers,
            min_density=body.min_density,
            min_crossings=body.min_crossings,
            auto_retry=body.auto_retry,
            max_retries=body.max_retries,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    background_tasks.add_task(execute_bulk_generation_job, job.id, session_factory)
    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "total": job.total,
    }


@router.post("/export/zip")
def export_bulk_zip(body: BulkZipExportIn, db: Session = Depends(get_db)):
    settings = ExportSettings(**body.settings.model_dump())
    try:
        zip_bytes = build_bulk_zip(
            db,
            puzzle_ids=body.puzzle_ids,
            job_id=body.job_id,
            kinds=body.kinds,
            formats=body.formats,
            force=body.force,
            settings=settings,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="crosswords_export.zip"'},
    )


@router.post("/export/book-pdf")
def export_bulk_book_pdf(body: BulkBookPdfExportIn, db: Session = Depends(get_db)):
    settings = ExportSettings(**body.settings.model_dump())
    try:
        pdf_bytes = build_combined_book_pdf(
            db,
            puzzle_ids=body.puzzle_ids,
            job_id=body.job_id,
            include_separate_clue_pages=body.include_separate_clue_pages,
            force=body.force,
            settings=settings,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="crossword_book.pdf"'},
    )
