from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from app.wordsearch.engine import GenerationError, generate_puzzle
from app.wordsearch.engine.models import ENGINE_VERSION
from app.wordsearch.importers import (ImportError_, ImportOptions, Issue, WordBank, WordEntry,
                           import_file)
from app.wordsearch.importers.models import chapter_label
from app.wordsearch.render import (HIGHLIGHT_STYLES, LayoutError, build_answer_key,
                        page_plan, render_answer_key_page, render_book_page,
                        resolve_title, section_page_number)
from app.wordsearch.render.fonts import available as available_fonts

from .jobs import store
from .schemas import (BankValidateIn, ChapterIn, ExportIn, JobIn, PreviewAnswersIn,
                      PreviewIn)

router = APIRouter(prefix="/api/wordsearch", tags=["wordsearch"])


# ------------------------------------------------------------------ helpers
def bank_from_payload(chapters: list[ChapterIn]) -> WordBank:
    bank = WordBank()
    top = 0
    for c in chapters:
        ch = bank.add_chapter(c.title)
        for w in c.words:
            ch.words.append(WordEntry(id=w.id, raw=w.raw or w.text, text=w.text.strip(),
                                      source=w.source))
            top = max(top, w.id)
    bank._next_id = top + 1
    return bank


def _entry_to_json(w: WordEntry) -> dict:
    return {"id": w.id, "raw": w.raw, "text": w.text, "source": w.source, "edited": w.edited}


def bank_to_json(bank: WordBank) -> list[dict]:
    return [{"title": c.title,
             "title_entry": _entry_to_json(c.title_entry) if c.title_entry else None,
             "words": [_entry_to_json(w) for w in c.words]} for c in bank.chapters]


def issue_json(i: Issue) -> dict:
    return {"severity": i.severity, "code": i.code, "message": i.message,
            "chapter": i.chapter, "word_id": i.word_id, "source": i.source,
            "chapter_index": i.chapter_index, "expected": i.expected, "actual": i.actual}


def problem(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message, **extra})


def gen_problem(e: GenerationError) -> JSONResponse:
    return problem(422, str(e), failed_words=e.failed_words, suggestions=e.suggestions,
                   sizes_tried=e.sizes_tried)


# --------------------------------------------------------------------- meta
@router.get("/health")
def health():
    return {"ok": True, "engine_version": ENGINE_VERSION,
            "highlight_styles": list(HIGHLIGHT_STYLES),
            "fonts": available_fonts()}


# ------------------------------------------------------------------- import
@router.post("/import")
async def api_import(file: UploadFile = File(...), layout: str = Form("auto"),
                     check_cross_chapter: bool = Form(False),
                     max_word_length: Optional[int] = Form(None),
                     split_commas: bool = Form(True),
                     sheet: Optional[str] = Form(None),
                     expected_words: Optional[int] = Form(None),
                     first_line_title: bool = Form(False)):
    data = await file.read()
    try:
        res = import_file(file.filename or "upload", data,
                          ImportOptions(layout=layout, split_commas=split_commas, sheet=sheet,
                                        first_line_title=first_line_title),
                          check_cross_chapter=check_cross_chapter,
                          max_word_length=max_word_length, expected_words=expected_words)
    except ImportError_ as e:
        return problem(400, str(e))
    return {"filename": res.filename, "sha256": res.sha256, "summary": res.summary(),
            "sheets": res.sheets, "size_bytes": len(data),
            "chapters": bank_to_json(res.bank), "issues": [issue_json(i) for i in res.issues]}


@router.post("/bank/validate")
def api_validate(body: BankValidateIn):
    bank = bank_from_payload(body.chapters)
    issues = bank.validate(body.rules.to_rules(), check_cross_chapter=body.check_cross_chapter,
                           max_word_length=body.max_word_length,
                           expected_words=body.expected_words)
    return {"issues": [issue_json(i) for i in issues], "summary": bank.stats(),
            "ready": not any(i.blocking for i in issues)}


@router.post("/bank/remove-duplicates")
def api_remove_duplicates(body: BankValidateIn):
    bank = bank_from_payload(body.chapters)
    removed = bank.remove_duplicates(body.rules.to_rules())
    issues = bank.validate(body.rules.to_rules(), check_cross_chapter=body.check_cross_chapter,
                           max_word_length=body.max_word_length,
                           expected_words=body.expected_words)
    return {"chapters": bank_to_json(bank),
            "removed": [{"chapter": t, "word": w.text, "id": w.id} for t, w in removed],
            "issues": [issue_json(i) for i in issues]}


# ------------------------------------------------------------------ preview
@router.post("/preview")
def api_preview(body: PreviewIn):
    if body.answer_style not in HIGHLIGHT_STYLES:
        return problem(422, f"Unknown highlight style {body.answer_style!r}")
    try:
        puz = generate_puzzle(body.words, body.config.to_config(body.seed),
                              puzzle_id=f"ch{body.index + 1:03d}")
        layout = body.layout.to_layout()
        layout.validate()
        ppp = layout.puzzles_per_page
        spp = body.solutions_per_page
        n_chapters = max(body.total_chapters or (body.index + 1),
                         body.index + 1 + len(body.extra_puzzles))
        total_pages = page_plan(n_chapters, ppp, spp)["total_pages"]

        puz_sec = body.index // ppp
        puz_page_no = (body.page_number if body.page_number is not None
                       else section_page_number("puzzle", puz_sec, n_chapters, ppp))
        page_items = [(puz, body.title, body.index)]
        for k, ex in enumerate(body.extra_puzzles[: max(0, ppp - 1)]):
            ex_idx = ex.index if ex.index is not None else (body.index + k + 1)
            ex_seed = ex.seed if ex.seed is not None else ((body.seed or 1) + k + 1)
            ex_puz = generate_puzzle(ex.words, body.config.to_config(ex_seed),
                                     puzzle_id=f"ch{ex_idx + 1:03d}")
            page_items.append((ex_puz, ex.title, ex_idx))

        sol_sec = body.index // spp
        sol_page_no = section_page_number("solution", sol_sec, n_chapters, ppp)
        by_idx = {it[2]: it for it in page_items}
        if body.solution_items:
            sol_items = []
            for k, it in enumerate(body.solution_items[:spp]):
                idx = it.index if it.index is not None else (sol_sec * spp + k)
                if idx in by_idx:
                    sol_items.append(by_idx[idx])
                else:
                    s_seed = it.seed if it.seed is not None else ((body.seed or 1) + k)
                    s_puz = generate_puzzle(it.words, body.config.to_config(s_seed),
                                            puzzle_id=f"ch{idx + 1:03d}")
                    sol_items.append((s_puz, it.title, idx))
        else:
            sol_items = [(puz, body.title, body.index)]

        return {
            "puzzle_svg": render_book_page("puzzle", page_items, layout, puz_page_no,
                                           total_pages),
            "answer_svg": render_book_page("solution", sol_items, layout, sol_page_no,
                                           total_pages, spp, body.answer_style),
            "resolved_title": resolve_title(layout, body.title, body.index),
            "rows": puz.rows, "cols": puz.cols, "seed": puz.seed,
            "sizes_tried": puz.sizes_tried, "directions": puz.directions,
            "key": [{"word": e.original, "start": e.start, "end": e.end,
                     "direction": e.direction_label} for e in build_answer_key(puz)]}
    except GenerationError as e:
        return gen_problem(e)
    except (LayoutError, ValueError) as e:
        return problem(422, f"Page layout problem: {e}")


@router.post("/preview/answers")
def api_preview_answers(body: PreviewAnswersIn):
    try:
        items = []
        for n, it in enumerate(body.items):
            idx = it.index if it.index is not None else n
            puz = generate_puzzle(it.words, body.config.to_config(
                it.seed if it.seed is not None else idx + 1), puzzle_id=f"pv{idx + 1}")
            items.append((puz, it.title, idx))
        svg = render_answer_key_page(items, body.per_page, body.layout.to_layout(),
                                     body.style, page_number=body.page_number)
        return {"svg": svg}
    except GenerationError as e:
        return gen_problem(e)
    except (LayoutError, ValueError) as e:
        return problem(422, str(e))


# --------------------------------------------------------------------- jobs
@router.post("/jobs")
def api_start_job(body: JobIn):
    try:
        body.layout.to_layout().validate()
    except LayoutError as e:
        return problem(422, f"Page layout problem: {e}")
    if body.expected_words is not None:     # never trust the UI alone
        wrong = [c for c in body.chapters if len(c.words) != body.expected_words]
        if wrong:
            msgs = []
            for c in wrong[:5]:
                n, diff = len(c.words), body.expected_words - len(c.words)
                det = f"Missing {diff}." if diff > 0 else f"Extra {-diff}."
                msgs.append(f"{chapter_label(c.index, c.title)} has {n} word"
                            f"{'' if n == 1 else 's'}. Expected {body.expected_words}. {det}")
            return problem(422, " ".join(msgs),
                           wrong_chapters=[c.index for c in wrong])
    job = store.start(body)
    return job.snapshot()


def _job(job_id: str):
    try:
        return store.get(job_id)
    except KeyError:
        raise HTTPException(404, "Unknown job")


@router.get("/jobs/{job_id}")
def api_job(job_id: str):
    return _job(job_id).snapshot()


@router.post("/jobs/{job_id}/cancel")
def api_cancel(job_id: str):
    job = _job(job_id)
    job.cancel_flag.set()
    return job.snapshot()


@router.post("/jobs/{job_id}/retry-failed")
def api_retry(job_id: str):
    job = _job(job_id)
    if not store.retry_failed(job):
        return problem(409, "Nothing to retry (job still running or no failures).")
    return job.snapshot()


@router.post("/jobs/{job_id}/export")
def api_export(job_id: str, body: ExportIn):
    job = _job(job_id)
    snap = job.snapshot()
    if snap["status"] == "running":
        return problem(409, "Wait for generation to finish before exporting.")
    if not snap["chapters"] or len(snap["chapters"]) < len(job.spec.chapters):
        return problem(409, "Cannot export a partial book: not all chapters have finished generating.")
    failed = [c for c in snap["chapters"] if not c["ok"]]
    if failed:
        msgs = [f"{chapter_label(c['index'], c['title'])}: {c['error']}" for c in failed]
        return problem(409, "Cannot export a partial book. " + " ".join(msgs),
                       failed_chapters=[c["index"] for c in failed])
    if not store.start_export(job, body):
        return problem(409, "An export is already running.")
    return job.snapshot()


class _CachedFileResponse(Response):
    """Streams a cached file from disk in 64KB chunks over ASGI."""

    def __init__(self, path: Path, media_type: str, headers: dict[str, str],
                 chunk_size: int = 64 * 1024):
        self.file_path = path
        self.chunk_size = chunk_size
        super().__init__(content=b"", media_type=media_type, headers=headers)

    async def __call__(self, scope, receive, send) -> None:
        size = self.file_path.stat().st_size
        raw_headers = [
            (k, v) for k, v in self.raw_headers if k.lower() != b"content-length"
        ]
        raw_headers.append((b"content-length", str(size).encode("latin-1")))
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": raw_headers,
        })
        with open(self.file_path, "rb") as fh:
            while True:
                chunk = fh.read(self.chunk_size)
                if not chunk:
                    break
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                })
        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })


@router.get("/jobs/{job_id}/download")
def api_download(job_id: str):
    job = _job(job_id)
    snap = job.snapshot()
    cache_path = Path(job.export_path) if job.export_path else None
    if snap["export"]["state"] != "done" or cache_path is None or not cache_path.exists():
        raise HTTPException(409, "Export is not ready")
    if snap["failed"] > 0 or len(snap["chapters"]) < len(job.spec.chapters):
        raise HTTPException(409, "Cannot download a partial book")
    name = "".join(c if c.isalnum() or c in "-_." else "_" for c in job.export_name)
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return _CachedFileResponse(
        cache_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )



