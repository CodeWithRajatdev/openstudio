"""Openstudio Unified Backend API (Word Search + Crossword Book Studio)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.crossword.db import init_db
from app.crossword.engine import EngineSettings, generate_crossword, preprocess_words
from app.crossword.routers import (
    bulk,
    clues,
    collections,
    export,
    imports,
    jobs,
    projects,
    puzzles,
)
from app.crossword.schemas import GenerateIn
from app.wordsearch.api.main import router as wordsearch_router
from app.wordsearch.engine.models import ENGINE_VERSION as WS_ENGINE_VERSION
from app.wordsearch.render import HIGHLIGHT_STYLES
from app.wordsearch.render.fonts import available as available_ws_fonts


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Openstudio", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Word Search Studio routes (/api/wordsearch/*)
app.include_router(wordsearch_router)

# Crossword Book Studio routes (/api/projects, /api/collections, /api/clues, /api/puzzles, ...)
app.include_router(imports.router)
app.include_router(projects.router)
app.include_router(collections.router)
app.include_router(clues.router)
app.include_router(jobs.router)
app.include_router(export.router)
app.include_router(puzzles.router)
app.include_router(bulk.router)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "status": "ok",
        "app": "Openstudio",
        "studios": ["wordsearch", "crossword"],
        "checkpoint": 7,
        "engine_version": WS_ENGINE_VERSION,
        "highlight_styles": list(HIGHLIGHT_STYLES),
        "fonts": available_ws_fonts(),
    }


@app.post("/api/engine/generate")
def engine_generate(body: GenerateIn):
    pre = preprocess_words(body.words, min_len=body.settings.min_word_length)
    result = generate_crossword(pre.accepted, EngineSettings(**body.settings.model_dump()))
    return {
        "status": result.status,
        "rows": result.rows,
        "cols": result.cols,
        "grid": ["".join(c or "#" for c in row) for row in result.cells],
        "entries": [
            {
                "answer": e.answer,
                "row": e.row,
                "col": e.col,
                "direction": e.direction,
                "number": e.number,
            }
            for e in result.entries
        ],
        "unplaced": [{"answer": u.answer, "reason": u.reason} for u in result.unplaced],
        "rejected_inputs": pre.rejected,
        "duplicate_inputs": pre.duplicates,
        "validation": asdict(result.validation),
        "stats": result.stats,
    }


# Serve built Openstudio frontend
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
