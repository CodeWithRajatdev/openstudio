"""SQLite-persisted background jobs and disk-cached PDF exports."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from app.wordsearch.engine import GenerationError
from app.wordsearch.engine.bulk import BulkResult, ChapterResult, generate_chapters
from app.wordsearch.engine.models import Placement, Puzzle
from app.wordsearch.export import PdfOptions, build_book_pdf, pdf_filename
from app.wordsearch.export.pdf import DEFAULT_PDF_CACHE_DIR
from app.wordsearch.render import LayoutError, layout_for_page, page_plan, render_puzzle_page

from .schemas import ExportIn, JobChapter, JobIn

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / ".cache" / "jobs.sqlite3"


def _puzzle_to_json(puzzle: Puzzle) -> str:
    return json.dumps({
        "puzzle_id": puzzle.puzzle_id,
        "rows": puzzle.rows,
        "cols": puzzle.cols,
        "grid": puzzle.grid,
        "placements": [
            {
                "puzzle_id": p.puzzle_id,
                "original": p.original,
                "grid_word": p.grid_word,
                "start_row": p.start_row,
                "start_col": p.start_col,
                "end_row": p.end_row,
                "end_col": p.end_col,
                "direction": p.direction,
            }
            for p in puzzle.placements
        ],
        "seed": puzzle.seed,
        "engine_version": puzzle.engine_version,
        "directions": puzzle.directions,
        "sizing_mode": puzzle.sizing_mode,
        "requested_size": list(puzzle.requested_size) if puzzle.requested_size else None,
        "sizes_tried": [list(s) for s in puzzle.sizes_tried],
    })


def _puzzle_from_json(raw: str) -> Puzzle:
    d = json.loads(raw)
    return Puzzle(
        puzzle_id=d["puzzle_id"],
        rows=d["rows"],
        cols=d["cols"],
        grid=d["grid"],
        placements=[Placement(**p) for p in d["placements"]],
        seed=d["seed"],
        engine_version=d["engine_version"],
        directions=d["directions"],
        sizing_mode=d["sizing_mode"],
        requested_size=tuple(d["requested_size"]) if d.get("requested_size") else None,
        sizes_tried=[tuple(s) for s in d.get("sizes_tried", [])],
    )


@dataclass
class Job:
    id: str
    spec: JobIn
    status: str = "running"            # running | done | cancelled
    done: int = 0
    total: int = 0
    cancel_flag: threading.Event = field(default_factory=threading.Event)
    export_state: str = "none"         # none | running | done | error
    export_message: str = ""
    export_path: Optional[str] = None
    export_size: int = 0
    export_name: str = "book.pdf"
    lock: threading.RLock = field(default_factory=threading.RLock)
    _store: Optional["JobStore"] = field(default=None, repr=False)

    @property
    def results(self) -> dict[int, ChapterResult]:
        if self._store is not None:
            return self._store._load_chapter_results(self.id)
        return {}

    @property
    def export_bytes(self) -> Optional[bytes]:
        if self.export_path:
            p = Path(self.export_path)
            if p.exists():
                return p.read_bytes()
        return None

    def snapshot(self) -> dict:
        if self._store is not None:
            return self._store.snapshot(self.id)
        return {
            "id": self.id,
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "succeeded": 0,
            "failed": 0,
            "chapters": [],
            "export": {
                "state": self.export_state,
                "message": self.export_message,
                "size": self.export_size,
                "name": self.export_name,
            },
        }

    def bulk_result(self) -> BulkResult:
        if self._store is not None:
            res_map = self._store._load_chapter_results(self.id)
            return BulkResult(chapters=[res_map[i] for i in sorted(res_map)])
        return BulkResult()


class JobStore:
    """SQLite-backed job and puzzle metadata store with disk-cached PDF exports."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None,
                 cache_dir: Optional[Union[str, Path]] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_PDF_CACHE_DIR
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.RLock()
        self._cancel_flags: dict[str, threading.Event] = {}
        self._job_locks: dict[str, threading.RLock] = {}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._db_lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    spec_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    export_state TEXT NOT NULL DEFAULT 'none',
                    export_message TEXT NOT NULL DEFAULT '',
                    export_path TEXT,
                    export_size INTEGER NOT NULL DEFAULT 0,
                    export_name TEXT NOT NULL DEFAULT 'book.pdf',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_chapters (
                    job_id TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    words_json TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    rows INTEGER,
                    cols INTEGER,
                    seed INTEGER,
                    puzzle_json TEXT,
                    error TEXT,
                    failed_words_json TEXT NOT NULL DEFAULT '[]',
                    sizes_tried_json TEXT NOT NULL DEFAULT '[]',
                    suggestions_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY (job_id, chapter_index),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
                """
            )

    def _cancel_event(self, job_id: str) -> threading.Event:
        with self._db_lock:
            ev = self._cancel_flags.get(job_id)
            if ev is None:
                ev = threading.Event()
                self._cancel_flags[job_id] = ev
            return ev

    def _job_lock(self, job_id: str) -> threading.RLock:
        with self._db_lock:
            lk = self._job_locks.get(job_id)
            if lk is None:
                lk = threading.RLock()
                self._job_locks[job_id] = lk
            return lk

    def get(self, job_id: str) -> Job:
        with self._db_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        spec = JobIn.model_validate_json(row["spec_json"])
        return Job(
            id=row["id"],
            spec=spec,
            status=row["status"],
            done=row["done"],
            total=row["total"],
            cancel_flag=self._cancel_event(job_id),
            export_state=row["export_state"],
            export_message=row["export_message"],
            export_path=row["export_path"],
            export_size=row["export_size"],
            export_name=row["export_name"],
            lock=self._job_lock(job_id),
            _store=self,
        )

    def snapshot(self, job_id: str) -> dict:
        with self._db_lock, self._connect() as conn:
            jrow = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if jrow is None:
                raise KeyError(job_id)
            crows = conn.execute(
                """
                SELECT chapter_index, title, ok, rows, cols, seed, error,
                       failed_words_json, suggestions_json
                FROM job_chapters
                WHERE job_id = ?
                ORDER BY chapter_index ASC
                """,
                (job_id,),
            ).fetchall()

        chapters = []
        for r in crows:
            chapters.append({
                "index": r["chapter_index"],
                "title": r["title"],
                "ok": bool(r["ok"]),
                "rows": r["rows"],
                "cols": r["cols"],
                "seed": r["seed"],
                "error": r["error"],
                "failed_words": json.loads(r["failed_words_json"] or "[]"),
                "suggestions": json.loads(r["suggestions_json"] or "[]"),
            })
        return {
            "id": jrow["id"],
            "status": jrow["status"],
            "done": jrow["done"],
            "total": jrow["total"],
            "succeeded": sum(1 for c in chapters if c["ok"]),
            "failed": sum(1 for c in chapters if not c["ok"]),
            "chapters": chapters,
            "export": {
                "state": jrow["export_state"],
                "message": jrow["export_message"],
                "size": jrow["export_size"],
                "name": jrow["export_name"],
            },
        }

    def _save_chapter_result(self, job_id: str, res: ChapterResult, done_count: int) -> None:
        puzzle_json = _puzzle_to_json(res.puzzle) if res.puzzle is not None else None
        rows = res.puzzle.rows if res.puzzle is not None else None
        cols = res.puzzle.cols if res.puzzle is not None else None
        seed = res.puzzle.seed if res.puzzle is not None else None
        error_msg = str(res.error) if res.error is not None else None
        failed_words = json.dumps(res.error.failed_words if res.error else [])
        sizes_tried = json.dumps([list(s) for s in (res.error.sizes_tried if res.error else [])])
        suggestions = json.dumps(res.error.suggestions if res.error else [])

        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO job_chapters (
                    job_id, chapter_index, title, words_json, ok,
                    rows, cols, seed, puzzle_json, error,
                    failed_words_json, sizes_tried_json, suggestions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    res.index,
                    res.title,
                    json.dumps(res.words),
                    1 if res.ok else 0,
                    rows,
                    cols,
                    seed,
                    puzzle_json,
                    error_msg,
                    failed_words,
                    sizes_tried,
                    suggestions,
                ),
            )
            conn.execute(
                "UPDATE jobs SET done = ? WHERE id = ?",
                (done_count, job_id),
            )

    def _load_chapter_results(self, job_id: str) -> dict[int, ChapterResult]:
        with self._db_lock, self._connect() as conn:
            crows = conn.execute(
                "SELECT * FROM job_chapters WHERE job_id = ? ORDER BY chapter_index ASC",
                (job_id,),
            ).fetchall()
        results: dict[int, ChapterResult] = {}
        for r in crows:
            puzzle = _puzzle_from_json(r["puzzle_json"]) if r["puzzle_json"] else None
            error = None
            if not r["ok"] and r["error"]:
                error = GenerationError(
                    r["error"],
                    failed_words=json.loads(r["failed_words_json"] or "[]"),
                    sizes_tried=[tuple(s) for s in json.loads(r["sizes_tried_json"] or "[]")],
                    suggestions=json.loads(r["suggestions_json"] or "[]"),
                )
            results[r["chapter_index"]] = ChapterResult(
                index=r["chapter_index"],
                title=r["title"],
                words=json.loads(r["words_json"]),
                puzzle=puzzle,
                error=error,
            )
        return results

    def start(self, spec: JobIn) -> Job:
        job_id = uuid.uuid4().hex[:12]
        ev = self._cancel_event(job_id)
        ev.clear()
        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, spec_json, status, done, total,
                    export_state, export_message, export_path, export_size, export_name, created_at
                ) VALUES (?, ?, 'running', 0, ?, 'none', '', NULL, 0, 'book.pdf', ?)
                """,
                (job_id, spec.model_dump_json(), len(spec.chapters), time.time()),
            )
        job = self.get(job_id)
        threading.Thread(target=self._run, args=(job_id, spec, list(spec.chapters)), daemon=True).start()
        return job

    def retry_failed(self, job: Job) -> bool:
        lk = self._job_lock(job.id)
        with lk:
            current = self.get(job.id)
            if current.status == "running":
                return False
            res_map = self._load_chapter_results(job.id)
            failed = [
                c for c in current.spec.chapters
                if c.index in res_map and not res_map[c.index].ok
            ]
            if not failed:
                return False
            ev = self._cancel_event(job.id)
            ev.clear()
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'running', done = 0, total = ? WHERE id = ?",
                    (len(failed), job.id),
                )
        threading.Thread(target=self._run, args=(job.id, current.spec, failed), daemon=True).start()
        return True

    def _run(self, job_id: str, spec: JobIn, chapters: list[JobChapter]) -> None:
        layout = spec.layout.to_layout()
        cfg = spec.config.to_config()
        total_pages = page_plan(len(spec.chapters), layout.puzzles_per_page)["total_pages"]
        cancel_ev = self._cancel_event(job_id)

        for n, ch in enumerate(chapters):
            if cancel_ev.is_set():
                break
            res = generate_chapters(
                [(ch.title, ch.words)],
                cfg,
                spec.base_seed,
                indices=[ch.index],
                seed_overrides=spec.seed_overrides,
            ).chapters[0]
            if res.ok:  # make sure it will also fit the page, fail early if not
                try:
                    page_no = (ch.index // layout.puzzles_per_page) + 1
                    render_puzzle_page(
                        [(res.puzzle, res.title, ch.index)],
                        layout_for_page(layout, page_no, total_pages),
                    )
                except LayoutError as e:
                    res.puzzle = None
                    res.error = GenerationError(
                        f"Puzzle generated but does not fit the page: {e}",
                        suggestions=[
                            "Go back to Step 3: use a larger trim size, smaller margins "
                            "or more clue columns."
                        ],
                    )
            self._save_chapter_result(job_id, res, n + 1)

        final_status = "cancelled" if cancel_ev.is_set() else "done"
        with self._db_lock, self._connect() as conn:
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (final_status, job_id))

    def start_export(self, job: Job, opts: ExportIn) -> bool:
        lk = self._job_lock(job.id)
        with lk:
            current = self.get(job.id)
            if current.export_state == "running" or current.status == "running":
                return False
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET export_state = 'running', export_message = '', export_path = NULL, export_size = 0
                    WHERE id = ?
                    """,
                    (job.id,),
                )
        threading.Thread(target=self._export, args=(job.id, opts), daemon=True).start()
        return True

    def _export(self, job_id: str, opts: ExportIn) -> None:
        try:
            current = self.get(job_id)
            bulk = current.bulk_result()
            if len(bulk.chapters) < len(current.spec.chapters):
                raise ValueError("Cannot export a partial book: not all chapters were generated.")
            export_name = pdf_filename(opts.project_name)
            cache_file = self.cache_dir / f"{job_id}-{export_name}"
            _, info = build_book_pdf(
                opts.project_name,
                bulk,
                current.spec.layout.to_layout(),
                PdfOptions(
                    per_page_answers=opts.per_page_answers,
                    answer_style=opts.answer_style,
                    page_numbers=opts.page_numbers,
                    include_answers=opts.include_answers,
                    title=opts.project_name,
                ),
                output_path=cache_file,
                return_bytes=False,
            )
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET export_state = 'done',
                        export_path = ?,
                        export_size = ?,
                        export_name = ?
                    WHERE id = ?
                    """,
                    (str(cache_file), info["bytes"], export_name, job_id),
                )
        except Exception as e:  # surfaced to the UI, never swallowed
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET export_state = 'error', export_message = ? WHERE id = ?",
                    (f"{type(e).__name__}: {e}", job_id),
                )


store = JobStore()
