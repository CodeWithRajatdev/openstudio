"""Project studio API endpoints: library CRUD, autosave, chapter import, JSON save/restore."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db, get_session_factory
from ..models import Collection, ImportBatch, Project, Puzzle
from ..schemas import (
    ChapterInlineActionIn,
    ProjectAcceptImportIn,
    ProjectCreateIn,
    ProjectPasteImportIn,
    ProjectRestoreJsonIn,
    ProjectSolutionPreviewIn,
    ProjectUpdateIn,
)
from ..services.export.geometry import ExportPuzzleData, build_solution_pages
from ..services.export.renderers import render_svg
from ..services.export.settings import ExportSettings
from ..services.export.verifier import PDFVerificationError
from ..services.projects import (
    accept_project_import,
    apply_chapter_inline_action,
    build_project_book_pdf,
    compute_project_page_plan,
    create_book_generation_job,
    create_project,
    delete_project,
    execute_book_generation_job,
    export_project_json,
    get_project_or_404,
    list_projects,
    resolve_chapter_display_title,
    restore_project_json,
    retry_failed_project_chapters,
    serialize_project,
    stage_project_import,
    update_project,
)
from ..services.puzzles import build_puzzle_export_data

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def get_projects(db: Session = Depends(get_db)):
    return list_projects(db)


@router.post("", status_code=201)
def post_project(body: ProjectCreateIn, db: Session = Depends(get_db)):
    project = create_project(
        db,
        name=body.name,
        project_type=body.project_type,
        trim_size=body.trim_size,
        current_step=body.current_step,
        settings=body.settings,
    )
    loaded = get_project_or_404(db, project.id)
    return serialize_project(db, loaded)


@router.post("/import-json", status_code=201)
def post_import_project_json(body: ProjectRestoreJsonIn, db: Session = Depends(get_db)):
    project = restore_project_json(db, body.model_dump())
    return serialize_project(db, project)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_project(db, project)


@router.patch("/{project_id}")
def patch_project(project_id: int, body: ProjectUpdateIn, db: Session = Depends(get_db)):
    try:
        project = update_project(
            db,
            project_id,
            name=body.name,
            project_type=body.project_type,
            trim_size=body.trim_size,
            current_step=body.current_step,
            settings=body.settings,
            import_metadata=body.import_metadata,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return serialize_project(db, project)


@router.put("/{project_id}")
def put_project(project_id: int, body: ProjectUpdateIn, db: Session = Depends(get_db)):
    return patch_project(project_id, body, db)


@router.delete("/{project_id}", status_code=204)
def remove_project(project_id: int, db: Session = Depends(get_db)):
    try:
        delete_project(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/imports")
async def stage_project_file_import(
    project_id: int,
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    collection_name: Optional[str] = Form(None),
    language: str = Form("en"),
    first_line_is_title: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if file is None and (text is None or not text.strip()):
        raise HTTPException(status_code=400, detail="Provide either a file upload or non-empty text")

    content_bytes = await file.read() if file is not None else None
    filename = file.filename if file is not None else None

    try:
        batch = stage_project_import(
            db,
            project,
            content_bytes=content_bytes,
            text=text,
            filename=filename,
            collection_name=collection_name,
            language=language,
            first_line_is_title=first_line_is_title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "id": batch.id,
        "project_id": batch.project_id,
        "filename": batch.filename,
        "source_format": batch.source_format,
        "status": batch.status,
        "report": batch.report,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


@router.post("/{project_id}/imports/paste")
def stage_project_paste_import(
    project_id: int,
    body: ProjectPasteImportIn,
    db: Session = Depends(get_db),
):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    batch = stage_project_import(
        db,
        project,
        text=body.text,
        collection_name=body.collection_name,
        language=body.language,
        first_line_is_title=body.first_line_is_title,
    )
    return {
        "id": batch.id,
        "project_id": batch.project_id,
        "filename": batch.filename,
        "source_format": batch.source_format,
        "status": batch.status,
        "report": batch.report,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


@router.post("/{project_id}/imports/{batch_id}/accept")
def accept_project_import_batch(
    project_id: int,
    batch_id: str,
    body: Optional[ProjectAcceptImportIn] = None,
    db: Session = Depends(get_db),
):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")

    try:
        return accept_project_import(
            db,
            project,
            batch,
            replace_existing=body.replace_existing if body else True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{project_id}/export-json")
def get_project_export_json(project_id: int, db: Session = Depends(get_db)):
    try:
        return export_project_json(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/chapters/{chapter_id}/action")
def post_chapter_inline_action(
    project_id: int,
    chapter_id: int,
    body: ChapterInlineActionIn,
    db: Session = Depends(get_db),
):
    try:
        return apply_chapter_inline_action(
            db,
            project_id,
            chapter_id,
            action=body.action,
            old_word=body.old_word,
            new_word=body.new_word,
            clue=body.clue,
            seed=body.seed,
            rows=body.rows,
            cols=body.cols,
            max_size=body.max_size,
            auto_retry=body.auto_retry,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/blocking-issues")
def get_project_blocking_issues(project_id: int, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = serialize_project(db, project)
    return {
        "project_id": project_id,
        "can_generate_and_download": data["can_generate_and_download"],
        "blocking_issues": data["blocking_issues"],
    }


@router.get("/{project_id}/page-plan")
def get_project_page_plan(project_id: int, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return compute_project_page_plan(db, project)


@router.post("/{project_id}/generate-and-download", status_code=202)
def post_project_generate_and_download(
    project_id: int,
    background_tasks: BackgroundTasks,
    regenerate: bool = Query(False),
    db: Session = Depends(get_db),
    session_factory=Depends(get_session_factory),
):
    try:
        job = create_book_generation_job(db, project_id, regenerate=regenerate)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        project = get_project_or_404(db, project_id)
        data = serialize_project(db, project)
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "blocking_issues": data["blocking_issues"],
            },
        ) from exc

    background_tasks.add_task(execute_book_generation_job, job.id, session_factory)
    return {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "total": job.total,
        "completed": job.completed,
        "failed": job.failed,
        "remaining": max(0, job.total - job.completed - job.failed),
    }


@router.get("/{project_id}/download-pdf")
def get_project_download_pdf(project_id: int, db: Session = Depends(get_db)):
    try:
        project = get_project_or_404(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        pdf_bytes, _plan, _ver, filename = build_project_book_pdf(db, project)
    except PermissionError as exc:
        data = serialize_project(db, project)
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "blocking_issues": data["blocking_issues"],
            },
        ) from exc
    except PDFVerificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{project_id}/retry-failed-chapters")
def post_retry_failed_chapters(project_id: int, db: Session = Depends(get_db)):
    try:
        return retry_failed_project_chapters(db, project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/solution-preview")
def post_project_solution_preview(
    project_id: int,
    body: ProjectSolutionPreviewIn,
    db: Session = Depends(get_db),
):
    """Render the multi-solution SVG page (1/2/4/6/8/9/12 per page) containing chapter_index."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    chapters = list(
        db.scalars(
            select(Collection)
            .where(Collection.project_id == project_id)
            .order_by(Collection.chapter_index.asc(), Collection.id.asc())
        ).all()
    )
    if not chapters:
        raise HTTPException(status_code=404, detail="No chapters in project")

    per_page = body.solutions_per_page if body.solutions_per_page in (1, 2, 4, 6, 8, 9, 12) else 4
    safe_idx = min(max(0, body.chapter_index), len(chapters) - 1)
    page_start = (safe_idx // per_page) * per_page
    slice_chapters = chapters[page_start : page_start + per_page]
    slice_ids = [ch.id for ch in slice_chapters]

    latest_by_col: dict[int, Puzzle] = {}
    if slice_ids:
        for p in db.scalars(
            select(Puzzle)
            .where(Puzzle.collection_id.in_(slice_ids))
            .options(selectinload(Puzzle.entries))
            .order_by(Puzzle.id.asc())
        ).all():
            if p.collection_id is not None:
                latest_by_col[p.collection_id] = p

    # Build real generated puzzles for the slice first, and keep a template puzzle
    # (preferring the active chapter's puzzle) to preview-fill any ungenerated slots
    # so the user always sees all `per_page` slots populated in the live preview.
    real_by_offset: dict[int, ExportPuzzleData] = {}
    fallback_exp: Optional[ExportPuzzleData] = None
    active_offset = safe_idx - page_start

    for offset, ch in enumerate(slice_chapters):
        puz = latest_by_col.get(ch.id)
        if puz is None:
            continue
        try:
            exp = build_puzzle_export_data(db, puz, force=True)
        except ValueError:
            continue
        real_by_offset[offset] = exp
        if offset == active_offset or fallback_exp is None:
            fallback_exp = exp

    if fallback_exp is None:
        raise HTTPException(status_code=404, detail="No generated puzzles available for solution preview")

    exp_puzzles: list[ExportPuzzleData] = []
    for slot_idx in range(per_page):
        if slot_idx < len(slice_chapters):
            ch = slice_chapters[slot_idx]
            puz_num = body.title_start_number + page_start + slot_idx
            base_exp = real_by_offset.get(slot_idx, fallback_exp)
            sol_title = resolve_chapter_display_title(
                ch.name,
                puz_num,
                mode=body.title_mode,
                template=body.title_template,
                enabled=body.title_enabled,
            )
        else:
            puz_num = body.title_start_number + page_start + slot_idx
            base_exp = fallback_exp
            sol_title = resolve_chapter_display_title(
                f"Sample Chapter {puz_num}",
                puz_num,
                mode=body.title_mode,
                template=body.title_template,
                enabled=body.title_enabled,
            )
        exp_puzzles.append(
            ExportPuzzleData(
                title=base_exp.title,
                solution_title=sol_title,
                rows=base_exp.rows,
                cols=base_exp.cols,
                grid=base_exp.grid,
                entries=base_exp.entries,
            )
        )

    settings = ExportSettings(**body.settings.model_dump())
    pages = build_solution_pages(
        exp_puzzles,
        settings,
        solutions_per_page=per_page,
        start_page_number=1,
    )
    svg_str = render_svg(pages[0])
    return Response(content=svg_str, media_type="image/svg+xml")



