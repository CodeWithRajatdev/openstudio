"""Checkpoint 5 tests: puzzle persistence, clue edit, regenerate keeping clue links, bulk jobs, ZIP & book PDF."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory
from app.main import app
from app.crossword.services.bulk import create_bulk_generation_job, execute_bulk_generation_job
from app.crossword.services.clues.ai import FakeAIProvider
from app.crossword.services.clues.dictionary import NullDictionaryProvider


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "puzzles_bulk_test.db"
    test_engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, future=True)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = lambda: TestingSessionLocal
    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_puzzle_persistence_export_block_and_single_clue_edit(db_setup):
    client, _ = db_setup
    # Import 3 crossing words where 1 has no clue
    csv_bytes = (
        "Word,Clue\n"
        "apple,Crisp orchard fruit.\n"
        "planet,Body orbiting a star.\n"
        "elephant,\n"
    ).encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("p1.csv", csv_bytes, "text/csv")}).json()
    col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

    gen_res = client.post(
        "/api/puzzles/generate",
        json={"collection_id": col_id, "title": "Unit 1", "clue_mode": "manual"},
    )
    assert gen_res.status_code == 201, gen_res.text
    puzzle = gen_res.json()
    puzzle_id = puzzle["id"]
    assert puzzle["validation"]["valid"] is True
    assert puzzle["clue_status"] == "incomplete"
    assert "ELEPHANT" in puzzle["missing_clues"]
    original_grid = puzzle["grid"]

    # Export is blocked without force=true when clues are incomplete
    blocked = client.get(f"/api/puzzles/{puzzle_id}/export?kind=puzzle&format=svg")
    assert blocked.status_code == 409

    # Export allowed with force=true
    forced = client.get(f"/api/puzzles/{puzzle_id}/export?kind=puzzle&format=svg&force=true")
    assert forced.status_code == 200
    assert "<svg" in forced.text

    # Edit the single missing clue -> grid untouched, clue_status becomes complete
    elephant_entry = next(e for e in puzzle["entries"] if e["answer"] == "ELEPHANT")
    edit_res = client.patch(
        f"/api/puzzles/{puzzle_id}/entries/{elephant_entry['id']}/clue",
        json={"text": "Largest land mammal with a trunk."},
    )
    assert edit_res.status_code == 200
    updated = edit_res.json()
    assert updated["grid"] == original_grid
    assert updated["clue_status"] == "complete"
    assert updated["missing_clues"] == []
    edited_entry = next(e for e in updated["entries"] if e["answer"] == "ELEPHANT")
    assert edited_entry["clue"] == "Largest land mammal with a trunk."
    assert edited_entry["clue_source"] == "manual"

    # Export now succeeds without force
    ok_export = client.get(f"/api/puzzles/{puzzle_id}/export?kind=puzzle_with_clues&format=svg")
    assert ok_export.status_code == 200


def test_puzzle_regenerate_retains_clue_links(db_setup):
    client, _ = db_setup
    csv_bytes = (
        "Word,Clue\n"
        "apple,Orchard fruit.\n"
        "planet,Space world.\n"
        "elephant,Trunked mammal.\n"
        "eagle,Bird of prey.\n"
    ).encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("p2.csv", csv_bytes, "text/csv")}).json()
    col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

    puzzle = client.post("/api/puzzles/generate", json={"collection_id": col_id}).json()
    puzzle_id = puzzle["id"]

    # Edit APPLE's clue manually
    apple_entry = next(e for e in puzzle["entries"] if e["answer"] == "APPLE")
    edited = client.patch(
        f"/api/puzzles/{puzzle_id}/entries/{apple_entry['id']}/clue",
        json={"text": "Custom edited clue for apple."},
    ).json()
    custom_clue_id = next(e for e in edited["entries"] if e["answer"] == "APPLE")["clue_id"]

    # Regenerate: remove EAGLE, replace PLANET -> PEAR, add ORANGE, change seed
    regen_res = client.post(
        f"/api/puzzles/{puzzle_id}/regenerate",
        json={
            "remove_words": ["eagle"],
            "replace_words": [{"old": "planet", "new": "pear", "clue": "Bell-shaped fruit."}],
            "add_words": [{"word": "orange", "clue": "Citrus fruit."}],
            "settings": {"seed": 7},
        },
    )
    assert regen_res.status_code == 200, regen_res.text
    regen = regen_res.json()
    assert regen["validation"]["valid"] is True
    assert regen["clue_status"] == "complete"

    by_ans = {e["answer"]: e for e in regen["entries"]}
    assert "EAGLE" not in by_ans
    assert "PEAR" in by_ans
    assert "ORANGE" in by_ans
    # Retained word APPLE kept its edited manual clue link!
    assert by_ans["APPLE"]["clue_id"] == custom_clue_id
    assert by_ans["APPLE"]["clue"] == "Custom edited clue for apple."


def test_bulk_isolation_splitting_zip_and_book_pdf(db_setup):
    client, SessionLocal = db_setup

    # Collection 1: 6 words (will be split with max_words_per_puzzle=3 into 2 puzzles)
    c1_csv = (
        "Word,Clue\n"
        "apple,Fruit one.\n"
        "planet,World two.\n"
        "elephant,Animal three.\n"
        "tiger,Cat four.\n"
        "eagle,Bird five.\n"
        "river,Stream six.\n"
    ).encode("utf-8")
    imp1 = client.post("/api/imports", files={"file": ("c1.csv", c1_csv, "text/csv")}).json()
    col1_id = client.post(f"/api/imports/{imp1['id']}/commit").json()["collections"][0]["id"]

    # Collection 2: Empty collection -> should fail in isolation without stopping others
    col2_id = client.post("/api/collections", json={"name": "Empty Set"}).json()["id"]

    # Collection 3: 3 words without clues -> bulk auto-generates clues first
    c3_csv = "Word\nlemon\nmelon\nmango\n".encode("utf-8")
    imp3 = client.post("/api/imports", files={"file": ("c3.csv", c3_csv, "text/csv")}).json()
    col3_id = client.post(f"/api/imports/{imp3['id']}/commit").json()["collections"][0]["id"]

    with SessionLocal() as db:
        job = create_bulk_generation_job(
            db,
            collection_ids=[col1_id, col2_id, col3_id],
            clue_mode="hybrid",
            difficulty="easy",
            generate_missing_clues=True,
            max_words_per_puzzle=3,
            max_workers=2,
        )
        job_id = job.id

    execute_bulk_generation_job(
        job_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(verify_succeeds=True),
        use_process_pool=False,
    )

    job_data = client.get(f"/api/jobs/{job_id}").json()
    assert job_data["status"] == "completed"
    assert job_data["total"] == 4       # 2 parts from col1 + 1 from col2 + 1 from col3
    assert job_data["completed"] == 3
    assert job_data["failed"] == 1
    assert len(job_data["result"]["puzzles"]) == 3
    assert len(job_data["result"]["failures"]) == 1
    assert job_data["result"]["failures"][0]["collection_id"] == col2_id

    # Bulk ZIP export
    zip_res = client.post(
        "/api/bulk/export/zip",
        json={
            "job_id": job_id,
            "kinds": ["puzzle", "answer_key"],
            "formats": ["svg", "pdf"],
        },
    )
    assert zip_res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_res.content), "r") as zf:
        names = zf.namelist()
        assert len(names) == 3 * 2 * 2  # 3 puzzles * 2 kinds * 2 formats
        assert any(n.endswith("/puzzle.svg") for n in names)
        assert any(n.endswith("/answer_key.pdf") for n in names)

    # Combined book PDF export (puzzles first, answer keys at the end)
    book_res = client.post(
        "/api/bulk/export/book-pdf",
        json={"job_id": job_id},
    )
    assert book_res.status_code == 200
    assert book_res.content.startswith(b"%PDF-")
    assert len(book_res.content) > 2500
