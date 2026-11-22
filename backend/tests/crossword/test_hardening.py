"""Checkpoint 7 hardening tests: large-list timing, 500-collection bulk run, deep SVG/PDF inspection."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine
from app.crossword.engine import EngineSettings, generate_crossword, preprocess_words
from app.crossword.models import Clue, Collection, CollectionWord, Puzzle, Word
from app.crossword.services.bulk import create_bulk_generation_job, execute_bulk_generation_job
from app.crossword.services.clues.ai import NullAIProvider
from app.crossword.services.clues.dictionary import NullDictionaryProvider
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from app.crossword.services.export.renderers import render_pdf, render_svg
from app.crossword.services.export.settings import ExportSettings


def test_large_list_timing_and_validity():
    vocab_40 = [
        "ASTRONOMY", "TELESCOPE", "PLANET", "GALAXY", "NEBULA", "ORBIT", "ECLIPSE", "GRAVITY",
        "ASTEROID", "COMET", "METEOR", "SATURN", "JUPITER", "MERCURY", "VENUS", "NEPTUNE",
        "URANUS", "COSMOS", "STARLIGHT", "QUASAR", "PULSAR", "SUPERNOVA", "HORIZON", "ZENITH",
        "SOLSTICE", "EQUINOX", "CRATER", "LUNAR", "SOLAR", "ROCKET", "CAPSULE", "SHUTTLE",
        "STATION", "VOYAGER", "APOLLO", "SPECTRUM", "RADIATION", "PHOTON", "CLUSTER", "PARSEC",
    ]
    t0 = time.perf_counter()
    pre = preprocess_words(vocab_40)
    assert len(pre.accepted) == 40
    res = generate_crossword(
        pre.accepted,
        EngineSettings(
            attempts_per_size=2,
            polish_attempts=1,
            max_nodes_per_attempt=1200,
            time_limit_s=15.0,
            seed=42,
        ),
    )
    elapsed = time.perf_counter() - t0
    assert res.validation.valid is True
    assert len(res.entries) + len(res.unplaced) == 40
    assert len(res.entries) >= 35
    assert elapsed < 16.0


def test_500_collection_bulk_run(tmp_path: Path):
    db_path = tmp_path / "bulk500.db"
    eng = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=eng)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eng, future=True)

    try:
        col_ids: list[int] = []
        with SessionLocal() as db:
            # Create shared vocabulary words with pre-approved clues for fast 500-collection bulk stress test
            base_words = [
                ("APPLE", "Crisp fruit."),
                ("PLANET", "Orbiting world."),
                ("ELEPHANT", "Trunked mammal."),
                ("EAGLE", "Raptor bird."),
                ("TIGER", "Striped cat."),
            ]
            word_objs: list[Word] = []
            for ans, clue_txt in base_words:
                w = Word(answer=ans, display=ans.lower(), language="en", difficulty="easy")
                db.add(w)
                db.flush()
                db.add(
                    Clue(
                        word_id=w.id,
                        text=clue_txt,
                        difficulty="easy",
                        source="import",
                        status="approved",
                    )
                )
                word_objs.append(w)

            for i in range(1, 501):
                c = Collection(name=f"Group {i:03d}", language="en")
                db.add(c)
                db.flush()
                col_ids.append(c.id)
                # Make collection #250 intentionally empty to verify failure isolation at scale
                if i == 250:
                    continue
                for pos, w in enumerate(word_objs):
                    db.add(CollectionWord(collection_id=c.id, word_id=w.id, position=pos))
            db.commit()

            job = create_bulk_generation_job(
                db,
                collection_ids=col_ids,
                engine_settings=EngineSettings(
                    attempts_per_size=1,
                    polish_attempts=0,
                    max_nodes_per_attempt=200,
                    time_limit_s=2.0,
                ),
                clue_mode="hybrid",
                difficulty="easy",
                generate_missing_clues=False,
                max_workers=1,
            )
            job_id = job.id

        execute_bulk_generation_job(
            job_id,
            SessionLocal,
            dictionary_provider=NullDictionaryProvider(),
            ai_provider=NullAIProvider(),
            use_process_pool=False,
        )

        with SessionLocal() as db:
            from app.crossword.models import Job

            finished = db.get(Job, job_id)
            assert finished is not None
            assert finished.status == "completed"
            assert finished.total == 500
            assert finished.completed == 499
            assert finished.failed == 1
            assert len(finished.result["puzzles"]) == 499
            assert len(finished.result["failures"]) == 1
            assert db.query(Puzzle).count() == 499
    finally:
        eng.dispose()


def test_svg_and_pdf_deep_inspection():
    entries = [
        ExportEntry(
            number=i,
            direction="A" if i % 2 else "D",
            row=0,
            col=0,
            answer="PLANET",
            clue=f"Detailed astronomical clue number {i} for deep inspection.",
        )
        for i in range(1, 55)
    ]
    puzzle = ExportPuzzleData(
        title="Inspection Puzzle",
        rows=5,
        cols=5,
        grid=["APPLE", "L###A", "P###R", "H###T", "A###H"],
        entries=entries,
    )
    settings = ExportSettings(page_size="6x9")

    for kind in ("puzzle", "clues", "answer_key", "puzzle_with_clues"):
        pages = build_export_pages(puzzle, kind, settings)
        for p in pages:
            svg_text = render_svg(p)
            root = ET.fromstring(svg_text)
            assert root.attrib["width"] == "432.00pt"
            assert root.attrib["height"] == "648.00pt"
            assert root.attrib["viewBox"] == "0 0 432.00 648.00"
            for el in root.iter():
                tag = el.tag.split("}")[-1]
                assert tag in {"svg", "rect", "line", "text"}

    # Inspect multi-page PDF structure, MediaBox, and embedded Vera TTF font
    combo_pages = build_export_pages(puzzle, "puzzle_with_clues", settings)
    assert len(combo_pages) >= 2
    pdf_bytes = render_pdf(combo_pages)
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes
    assert b"BitstreamVeraSans" in pdf_bytes
    assert re.search(rb"/MediaBox\s*\[\s*0(?:\.0+)?\s+0(?:\.0+)?\s+432(?:\.0+)?\s+648(?:\.0+)?\s*\]", pdf_bytes)
    page_markers = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(page_markers) == len(combo_pages)
