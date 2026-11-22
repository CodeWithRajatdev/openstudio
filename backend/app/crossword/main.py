"""Woodpecker Crossword Generator API."""
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .engine import EngineSettings, generate_crossword, preprocess_words
from .routers import bulk, clues, collections, export, imports, jobs, projects, puzzles
from .schemas import GenerateIn


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Woodpecker Crossword Generator", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)
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
    return {"status": "ok", "checkpoint": 7}


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
            {"answer": e.answer, "row": e.row, "col": e.col, "direction": e.direction, "number": e.number}
            for e in result.entries
        ],
        "unplaced": [{"answer": u.answer, "reason": u.reason} for u in result.unplaced],
        "rejected_inputs": pre.rejected,
        "duplicate_inputs": pre.duplicates,
        "validation": asdict(result.validation),
        "stats": result.stats,
    }
