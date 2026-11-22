"""Phase 3 tests: clue defaults, alternatives & history, render-time styling, blocking list & Alembic."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory, run_migrations
from app.main import app
from app.crossword.models import Clue
from app.crossword.services.clues.ai import FakeAIProvider
from app.crossword.services.clues.dictionary import NullDictionaryProvider, WordNetDictionaryProvider
from app.crossword.services.clues.service import create_clue_generation_job, execute_clue_generation_job
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from app.crossword.services.export.renderers import render_svg
from app.crossword.services.export.settings import ExportSettings


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "phase3_test.db"
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


def test_dictionary_clues_default_to_needs_review_and_ai_approved_only_when_verified(db_setup):
    client, SessionLocal = db_setup
    csv_bytes = "Word\napple\napples\n".encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("c.csv", csv_bytes, "text/csv")}).json()
    col1_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

    # Unverified run: both dictionary (apple) and AI (apples) default to needs_review
    with SessionLocal() as db:
        job1 = create_clue_generation_job(db, collection_id=col1_id, mode="automatic", difficulty="medium", verify=False)
        job1_id = job1.id
    execute_clue_generation_job(
        job1_id,
        SessionLocal,
        dictionary_provider=WordNetDictionaryProvider(),
        ai_provider=FakeAIProvider(verify_succeeds=True),
    )
    sum1 = client.get(f"/api/collections/{col1_id}/clues?mode=automatic&difficulty=medium").json()
    by_ans1 = {it["answer"]: it["active_clue"] for it in sum1["items"]}
    assert by_ans1["APPLE"]["source"] == "dictionary"
    assert by_ans1["APPLE"]["status"] == "needs_review"
    assert by_ans1["APPLES"]["source"] == "ai"
    assert by_ans1["APPLES"]["status"] == "needs_review"

    # AI with verify=True but reverse-solve fails -> needs_review
    imp2 = client.post("/api/imports", files={"file": ("b.csv", b"Word\nbananas\n", "text/csv")}).json()
    col2_id = client.post(f"/api/imports/{imp2['id']}/commit").json()["collections"][0]["id"]
    with SessionLocal() as db:
        job2 = create_clue_generation_job(db, collection_id=col2_id, mode="automatic", difficulty="medium", verify=True)
        job2_id = job2.id
    execute_clue_generation_job(
        job2_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(verify_succeeds=False),
    )
    sum2 = client.get(f"/api/collections/{col2_id}/clues?mode=automatic&difficulty=medium").json()
    assert sum2["items"][0]["active_clue"]["source"] == "ai"
    assert sum2["items"][0]["active_clue"]["status"] == "needs_review"

    # AI with verify=True and reverse-solve passes -> approved
    imp3 = client.post("/api/imports", files={"file": ("o.csv", b"Word\noranges\n", "text/csv")}).json()
    col3_id = client.post(f"/api/imports/{imp3['id']}/commit").json()["collections"][0]["id"]
    with SessionLocal() as db:
        job3 = create_clue_generation_job(db, collection_id=col3_id, mode="automatic", difficulty="medium", verify=True)
        job3_id = job3.id
    execute_clue_generation_job(
        job3_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(verify_succeeds=True),
    )
    sum3 = client.get(f"/api/collections/{col3_id}/clues?mode=automatic&difficulty=medium").json()
    assert sum3["items"][0]["active_clue"]["source"] == "ai"
    assert sum3["items"][0]["active_clue"]["status"] == "approved"


def test_regenerate_single_clue_offers_alternatives_and_preserves_history_for_restore(db_setup, monkeypatch):
    client, _ = db_setup
    monkeypatch.setenv("AI_PROVIDER", "fake")
    from app.crossword.config import get_settings

    get_settings.cache_clear()
    try:
        csv_bytes = "Word,Clue\napple,Crisp orchard fruit\n".encode("utf-8")
        imp = client.post("/api/imports", files={"file": ("a.csv", csv_bytes, "text/csv")}).json()
        col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

        summary = client.get(f"/api/collections/{col_id}/clues?mode=hybrid&difficulty=medium").json()
        word_id = summary["items"][0]["word_id"]
        imported_clue_id = summary["items"][0]["active_clue"]["id"]

        # Regenerate single clue -> offers 2 to 3 alternatives, keeps imported clue intact
        regen = client.post(
            f"/api/words/{word_id}/clues/regenerate",
            json={"difficulty": "medium", "count": 3},
        )
        assert regen.status_code == 200, regen.text
        regen_data = regen.json()
        alts = regen_data["alternatives"]
        assert 2 <= len(alts) <= 3
        assert len({a["text"] for a in alts}) == len(alts)
        assert any(c["id"] == imported_clue_id and c["text"] == "Crisp orchard fruit" for c in regen_data["history"])

        # Pick an alternative -> becomes active & approved, previous clue kept in history
        chosen_id = alts[0]["id"]
        sel = client.post(
            f"/api/words/{word_id}/clues/select",
            json={"clue_id": chosen_id},
        )
        assert sel.status_code == 200, sel.text
        sel_data = sel.json()
        assert sel_data["active_clue"]["id"] == chosen_id
        assert sel_data["active_clue"]["status"] == "approved"
        assert any(c["id"] == imported_clue_id and c["text"] == "Crisp orchard fruit" for c in sel_data["history"])

        # Restore original imported clue -> becomes active again, alternatives remain in history
        restored = client.post(f"/api/words/{word_id}/clues/{imported_clue_id}/restore")
        assert restored.status_code == 200, restored.text
        rest_data = restored.json()
        assert rest_data["active_clue"]["id"] == imported_clue_id
        assert rest_data["active_clue"]["text"] == "Crisp orchard fruit"
        assert any(c["id"] == chosen_id for c in rest_data["history"])
    finally:
        get_settings.cache_clear()


def test_mode_and_difficulty_changes_never_delete_manual_or_imported_clues(db_setup, monkeypatch):
    client, SessionLocal = db_setup
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("DICTIONARY_PROVIDER", "none")
    from app.crossword.config import get_settings

    get_settings.cache_clear()
    try:
        csv_bytes = "Word,Clue\napple,Orchard snack.\n".encode("utf-8")
        imp = client.post("/api/imports", files={"file": ("m.csv", csv_bytes, "text/csv")}).json()
        col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

        summary = client.get(f"/api/collections/{col_id}/clues").json()
        word_id = summary["items"][0]["word_id"]
        import_clue_id = summary["items"][0]["active_clue"]["id"]

        manual = client.post(
            f"/api/words/{word_id}/clues",
            json={"text": "Red tree fruit.", "difficulty": "easy"},
        ).json()
        manual_clue_id = manual["id"]

        # Editing an imported clue creates a new manual clue instead of overwriting the import row
        client.patch(f"/api/clues/{import_clue_id}", json={"text": "Edited crisp snack."})

        # Generate automatic clues for easy and hard and switch modes
        for diff in ("easy", "hard"):
            client.post(
                "/api/clues/generate",
                json={"collection_id": col_id, "mode": "automatic", "difficulty": diff, "verify": True},
            )
        for m in ("manual", "automatic", "hybrid"):
            for d in ("easy", "medium", "hard"):
                res = client.get(f"/api/collections/{col_id}/clues?mode={m}&difficulty={d}")
                assert res.status_code == 200

        with SessionLocal() as db:
            all_clues = list(db.scalars(select(Clue).where(Clue.word_id == word_id)).all())
            by_id = {c.id: c for c in all_clues}
            assert import_clue_id in by_id
            assert by_id[import_clue_id].text == "Orchard snack."
            assert by_id[import_clue_id].source == "import"
            assert manual_clue_id in by_id
            assert by_id[manual_clue_id].text == "Red tree fruit."
            assert by_id[manual_clue_id].source == "manual"
    finally:
        get_settings.cache_clear()


def test_clue_style_settings_applied_at_render_time_without_mutating_stored_text(db_setup):
    client, SessionLocal = db_setup
    csv_bytes = "Word,Clue\napple,Sweet orchard fruit.\n".encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("s.csv", csv_bytes, "text/csv")}).json()
    col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]
    clue_id = client.get(f"/api/collections/{col_id}/clues").json()["items"][0]["active_clue"]["id"]

    puzzle = ExportPuzzleData(
        title="Style Test",
        rows=5,
        cols=5,
        grid=["APPLE"] + ["#####"] * 4,
        entries=[
            ExportEntry(
                number=1,
                direction="A",
                row=0,
                col=0,
                answer="APPLE",
                clue="Sweet orchard fruit.",
                display="apple",
            )
        ],
    )

    def _svg_text(cap: str, punct: str, show_len: bool) -> str:
        pages = build_export_pages(
            puzzle,
            "clues",
            ExportSettings(
                page_size="letter",
                clue_capitalization=cap,
                clue_ending_punctuation=punct,
                show_clue_lengths=show_len,
            ),
        )
        root = ET.fromstring(render_svg(pages[0]))
        return " ".join(el.text or "" for el in root.iter() if el.tag.endswith("text"))

    upper_none = _svg_text("uppercase", "none", False)
    assert "1. SWEET ORCHARD FRUIT" in upper_none
    assert "(5)" not in upper_none

    lower_period = _svg_text("lowercase", "period", True)
    assert "1. sweet orchard fruit. (5)" in lower_period

    title_none = _svg_text("title", "none", True)
    assert "1. Sweet Orchard Fruit (5)" in title_none

    # Stored Clue.text in database must remain completely untouched
    with SessionLocal() as db:
        stored = db.get(Clue, clue_id)
        assert stored is not None
        assert stored.text == "Sweet orchard fruit."


def test_missing_clues_blocking_list_names_exact_words_and_blocks_download(db_setup):
    client, _ = db_setup
    pid = client.post("/api/projects", json={"name": "Blocking Test"}).json()["id"]
    paste_text = (
        "Chapter,Word,Clue\n"
        "Chapter 1,cat,Small feline\n"
        "Chapter 1,car,Road vehicle\n"
        "Chapter 1,tar,Road pitch\n"
        "Chapter 2,apple,Orchard fruit\n"
        "Chapter 2,planet,\n"
        "Chapter 2,elephant,\n"
    )
    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    accepted = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept").json()
    proj = accepted["project"]

    assert proj["can_generate_and_download"] is False
    missing_block = next(b for b in proj["blocking_issues"] if b["type"] == "missing_clues")
    assert missing_block["chapter_name"] == "Chapter 2"
    assert missing_block["words"] == ["PLANET", "ELEPHANT"]
    assert "PLANET" in missing_block["message"] and "ELEPHANT" in missing_block["message"]

    block_ep = client.get(f"/api/projects/{pid}/blocking-issues").json()
    assert block_ep["can_generate_and_download"] is False

    dl = client.post(f"/api/projects/{pid}/generate-and-download")
    assert dl.status_code == 409
    detail_str = str(dl.json()["detail"])
    assert "PLANET" in detail_str and "ELEPHANT" in detail_str


def test_alembic_upgrades_legacy_and_fresh_databases(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    eng = create_db_engine(f"sqlite:///{db_path}")
    try:
        # Build a pre-Phase-1 legacy schema without projects or the new Phase 1 columns
        with eng.begin() as conn:
            conn.execute(text("""
                CREATE TABLE words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    answer VARCHAR(64) NOT NULL,
                    display VARCHAR(128) NOT NULL,
                    language VARCHAR(16) NOT NULL,
                    difficulty VARCHAR(16),
                    category VARCHAR(128),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    UNIQUE (answer, language)
                )
            """))
            conn.execute(text("""
                CREATE TABLE clues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    difficulty VARCHAR(16),
                    source VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    language VARCHAR(16) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE collection_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    UNIQUE (collection_id, word_id)
                )
            """))
            conn.execute(text("""
                CREATE TABLE puzzles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id INTEGER REFERENCES collections(id) ON DELETE SET NULL,
                    title VARCHAR(255) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    clue_status VARCHAR(32) NOT NULL,
                    rows INTEGER NOT NULL,
                    cols INTEGER NOT NULL,
                    grid JSON NOT NULL,
                    settings JSON NOT NULL,
                    validation JSON NOT NULL,
                    unplaced JSON NOT NULL,
                    stats JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE puzzle_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puzzle_id INTEGER NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
                    word_id INTEGER REFERENCES words(id) ON DELETE SET NULL,
                    clue_id INTEGER REFERENCES clues(id) ON DELETE SET NULL,
                    answer VARCHAR(64) NOT NULL,
                    number INTEGER NOT NULL,
                    direction VARCHAR(1) NOT NULL,
                    row INTEGER NOT NULL,
                    col INTEGER NOT NULL,
                    length INTEGER NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE jobs (
                    id VARCHAR(64) PRIMARY KEY,
                    type VARCHAR(64) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    total INTEGER NOT NULL,
                    completed INTEGER NOT NULL,
                    failed INTEGER NOT NULL,
                    payload JSON NOT NULL,
                    result JSON NOT NULL,
                    error TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE import_batches (
                    id VARCHAR(64) PRIMARY KEY,
                    filename VARCHAR(255),
                    source_format VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    report JSON NOT NULL,
                    staged_data JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(
                text(
                    "INSERT INTO collections (name, language, created_at, updated_at) "
                    "VALUES ('Legacy Chapter', 'en', '2026-01-01', '2026-01-01')"
                )
            )

        # Upgrade via Alembic
        run_migrations(eng)

        insp = inspect(eng)
        tables = set(insp.get_table_names())
        assert "alembic_version" in tables
        assert "projects" in tables

        col_names = {c["name"] for c in insp.get_columns("collections")}
        assert {"project_id", "chapter_index", "chapter_meta"}.issubset(col_names)

        cw_names = {c["name"] for c in insp.get_columns("collection_words")}
        assert {"display", "raw_word", "raw_clue", "cell_ref", "extra_data", "clue_id"}.issubset(cw_names)

        pe_names = {c["name"] for c in insp.get_columns("puzzle_entries")}
        assert "display" in pe_names

        ib_names = {c["name"] for c in insp.get_columns("import_batches")}
        assert "project_id" in ib_names

        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory
        from app.crossword.db import BACKEND_DIR

        acfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
        acfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        expected_head = ScriptDirectory.from_config(acfg).get_current_head()

        with eng.connect() as conn:
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert ver == expected_head
            legacy_name = conn.execute(text("SELECT name FROM collections")).scalar_one()
            assert legacy_name == "Legacy Chapter"
    finally:
        eng.dispose()
