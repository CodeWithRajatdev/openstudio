"""Phase 6 hardening tests: parity binding gutter, edge cases, enumerations, verifier, reproducibility, migrations, 100-chapter benchmark & security."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.crossword.services.export.book import (
    assemble_book_pages_and_plan,
    build_book_pdf,
    compute_book_page_plan,
)
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData
from app.crossword.services.export.primitives import LinePrimitive, RectPrimitive, TextPrimitive
from app.crossword.services.export.settings import ExportSettings


def _sample_export_puzzle(title: str, entry_count: int = 3) -> ExportPuzzleData:
    entries = [
        ExportEntry(number=1, direction="A", row=0, col=0, answer="CAT", clue="Small feline", display="cat"),
        ExportEntry(number=1, direction="D", row=0, col=0, answer="CAR", clue="Road vehicle", display="car"),
        ExportEntry(number=2, direction="D", row=0, col=2, answer="TAR", clue="Dark road pitch", display="tar"),
    ][:entry_count]
    return ExportPuzzleData(
        title=title,
        rows=3,
        cols=3,
        grid=["CAT", "A#A", "R#R"],
        entries=entries,
    )


def test_step0_binding_gutter_alternates_by_page_parity():
    chapters = [
        (1, "Chapter One", _sample_export_puzzle("Chapter One")),
        (2, "Chapter Two", _sample_export_puzzle("Chapter Two")),
        (3, "Chapter Three", _sample_export_puzzle("Chapter Three")),
    ]
    settings = ExportSettings(
        page_size="6x9",
        margin_left=36.0,
        margin_right=36.0,
        margin_top=36.0,
        margin_bottom=36.0,
        gutter=24.0,
        font_family="Open Sans",
    )

    pages, plan = assemble_book_pages_and_plan(chapters, settings, solutions_per_page=4)
    pdf_bytes, built_plan, verification = build_book_pdf(chapters, settings, solutions_per_page=4)

    assert verification["valid"] is True
    assert plan["total_pages"] == built_plan["total_pages"] == len(PdfReader(io.BytesIO(pdf_bytes)).pages)

    # Page 1 (odd / recto): spine is on left -> content box shifted right by gutter
    p1_texts = [p for p in pages[0].primitives if isinstance(p, TextPrimitive) and p.text == "Chapter One"]
    assert p1_texts and pytest.approx(p1_texts[0].x, abs=0.01) == 60.0

    # Page 2 (even / verso): spine is on right -> content box starts at left margin (36.0), shifted left relative to Page 1
    p2_texts = [p for p in pages[1].primitives if isinstance(p, TextPrimitive) and p.text == "Chapter Two"]
    assert p2_texts and pytest.approx(p2_texts[0].x, abs=0.01) == 36.0

    # Page 3 (odd / recto): shifts back to 60.0
    p3_texts = [p for p in pages[2].primitives if isinstance(p, TextPrimitive) and p.text == "Chapter Three"]
    assert p3_texts and pytest.approx(p3_texts[0].x, abs=0.01) == 60.0

    # Solutions start on Page 4 (even / verso): header & solution grid content box must also respect even-page parity
    p4_texts = [p for p in pages[3].primitives if isinstance(p, TextPrimitive) and p.text == "Solutions"]
    assert p4_texts and pytest.approx(p4_texts[0].x, abs=0.01) == 36.0

    # Compare outer border line bounding box centers on page 1 vs page 2 (must differ by gutter = 24pt)
    p1_lines = [p for p in pages[0].primitives if isinstance(p, LinePrimitive)]
    p2_lines = [p for p in pages[1].primitives if isinstance(p, LinePrimitive)]
    p1_center = (min(l.x1 for l in p1_lines) + max(l.x2 for l in p1_lines)) / 2.0
    p2_center = (min(l.x1 for l in p2_lines) + max(l.x2 for l in p2_lines)) / 2.0
    assert pytest.approx(p1_center - p2_center, abs=0.1) == 24.0


# ---------------------------------------------------------------------------
# Phase 6 Step 1 Tests (written failing first)
# ---------------------------------------------------------------------------

import itertools
import sqlite3
import time

import openpyxl
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory, run_migrations
from app.crossword.engine import format_enumeration
from app.main import app
from app.crossword.services.clues.ai import FakeAIProvider
from app.crossword.services.clues.dictionary import NullDictionaryProvider
from app.crossword.services.clues.service import create_clue_generation_job, execute_clue_generation_job
from app.crossword.services.export.verifier import PDFVerificationError, verify_pdf
from app.crossword.services.importer import parse_import_payload


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "phase6_test.db"
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


def test_phase6_chapter_import_edge_cases():
    # 1. Text/CSV with leading blanks, whitespace-only rows, runs of blank lines,
    #    spaces inside words, header skip, extra columns, within-chapter & cross-chapter duplicates,
    #    and trailing blank lines.
    raw_csv = (
        "\n"
        "   \n"
        "Word,Clue,Difficulty,Notes\n"
        "ice cream,Frozen dessert,easy,keep_note\n"
        "tiger,Striped cat,easy,\n"
        "   tiger ,Duplicate tiger in ch1,easy,\n"
        "\n"
        "\t\n"
        "\n"
        "eagle,Soaring raptor,easy,extra_info\n"
        "ice cream,Across chapter duplicate,medium,\n"
        "  \n"
        "\n"
    )
    fmt, report, _ = parse_import_payload(text=raw_csv, filename="chapters.csv")
    assert fmt == "csv"
    assert report["group_count"] == 2
    assert report["skipped_header_count"] == 1
    assert report["extra_column_count"] == 2
    assert report["duplicate_count"] == 1
    assert report["leading_blank_row_count"] == 2
    assert report["trailing_blank_row_count"] == 2
    assert report["cross_chapter_duplicate_count"] == 1
    assert any(d["answer"] == "ICECREAM" for d in report["cross_chapter_duplicates"])

    # Spaces inside "ice cream" must NOT split a chapter
    assert report["groups"][0]["valid_count"] == 2
    assert report["groups"][1]["valid_count"] == 2

    # 2. Multi-sheet .xlsx imported in exact sheet order
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Sheet Alpha"
    ws1.append(["Word", "Clue"])
    ws1.append(["apple", "Red fruit"])
    ws2 = wb.create_sheet("Sheet Beta")
    ws2.append(["Word", "Clue"])
    ws2.append(["river", "Flowing water"])
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)

    xfmt, xreport, _ = parse_import_payload(
        content_bytes=xlsx_buf.getvalue(),
        filename="multi_sheet.xlsx",
    )
    assert xfmt == "excel"
    assert [g["name"] for g in xreport["groups"]] == ["Sheet Alpha", "Sheet Beta"]


def test_phase6_enumeration_display_styles(db_setup):
    assert format_enumeration("ICECREAM", "ice cream", style="formatted") == "(3,5)"
    assert format_enumeration("XRAY", "x-ray", style="formatted") == "(1-3)"
    assert format_enumeration("CATSCRADLE", "cat's cradle", style="formatted") == "(4,6)"
    assert format_enumeration("ROCKNROLL", "rock 'n' roll", style="formatted") == "(4,1,4)"
    assert (
        format_enumeration("MOTHERINLAWSFRIEND", "mother-in-law's friend", style="formatted")
        == "(6-2-4,6)"
    )
    assert format_enumeration("ICECREAM", "ice cream", style="total") == "(8)"
    assert format_enumeration("ICECREAM", "ice cream", style="none") == ""

    client, _ = db_setup
    proj = client.post(
        "/api/projects",
        json={"name": "Enum Book", "settings": {"enumeration_display": "total"}},
    ).json()
    staged = client.post(
        f"/api/projects/{proj['id']}/imports/paste",
        json={
            "text": "ice cream, Sweet frozen treat\nx-ray, Medical imaging beam\napple, Crisp orchard fruit\neagle, Majestic raptor",
            "collection_name": "Ch1",
        },
    ).json()
    acc = client.post(
        f"/api/projects/{proj['id']}/imports/{staged['id']}/accept",
        json={"replace_existing": True},
    ).json()
    ch_id = acc["project"]["chapters"][0]["id"]

    # Collection endpoint must honor enumeration_display query param
    col_total = client.get(f"/api/collections/{ch_id}?enumeration_display=total").json()
    by_ans = {w["answer"]: w for w in col_total["words"]}
    assert by_ans["ICECREAM"]["enumeration"] == "(8)"
    assert by_ans["XRAY"]["enumeration"] == "(4)"

    col_none = client.get(f"/api/collections/{ch_id}?enumeration_display=none").json()
    assert next(w for w in col_none["words"] if w["answer"] == "ICECREAM")["enumeration"] == ""

    # Generated puzzle serializer must apply project's enumeration_display="total"
    puz = client.post(
        "/api/puzzles/generate",
        json={"collection_id": ch_id, "settings": {"min_word_length": 3}},
    ).json()
    puz_entry = next(e for e in puz["entries"] if e["answer"] == "ICECREAM")
    assert puz_entry["enumeration"] == "(8)"


def test_phase6_page_plan_matrix():
    long_clue_puzzle = ExportPuzzleData(
        title="Long Clue Chapter",
        rows=3,
        cols=3,
        grid=["CAT", "A#A", "R#R"],
        entries=[
            ExportEntry(
                number=i,
                direction="A" if i % 2 else "D",
                row=0,
                col=0,
                answer="PLANET",
                clue=f"Detailed descriptive clue #{i} crafted long enough to wrap and push across multiple clue pages.",
                display="planet",
            )
            for i in range(1, 35)
        ],
    )
    settings = ExportSettings(
        page_size="6x9",
        margin_left=36.0,
        margin_right=36.0,
        gutter=24.0,
        font_family="Open Sans",
    )

    import math

    for spp in (1, 2, 4, 6, 8, 9, 12):
        chapters = [
            (i, f"Ch {i}", long_clue_puzzle if i == 1 else _sample_export_puzzle(f"Ch {i}"))
            for i in range(1, 14)
        ]
        plan_std = compute_book_page_plan(
            chapters,
            settings,
            solutions_per_page=spp,
            start_puzzles_on_right_hand_page=False,
        )
        plan_rhs = compute_book_page_plan(
            chapters,
            settings,
            solutions_per_page=spp,
            start_puzzles_on_right_hand_page=True,
        )
        assert plan_std["solutions_per_page"] == spp
        assert plan_std["solution_pages"] == math.ceil(len(chapters) / spp)
        assert plan_std["front_matter_blank_pages"] == 0
        assert plan_rhs["front_matter_blank_pages"] == 1
        assert plan_std["total_pages"] % 2 == 0
        assert plan_rhs["total_pages"] % 2 == 0
        assert plan_std["chapters"][0]["puzzle_pages"] >= 2
        assert pytest.approx(plan_std["odd_page_content_x_pt"], abs=0.01) == 60.0
        assert pytest.approx(plan_std["even_page_content_x_pt"], abs=0.01) == 36.0
        assert pytest.approx(plan_std["content_width_pt"], abs=0.01) == plan_std["width_pt"] - 96.0

    # Build a verified PDF with 12 chapters and solutions_per_page=12 (must fit on 1 solution page)
    twelve_chapters = [(i, f"Ch {i}", _sample_export_puzzle(f"Ch {i}")) for i in range(1, 13)]
    pdf_12, plan_12, ver_12 = build_book_pdf(twelve_chapters, settings, solutions_per_page=12)
    assert plan_12["solutions_per_page"] == 12
    assert plan_12["solution_pages"] == 1
    assert ver_12["valid"] is True


def test_phase6_verify_pdf_all_failure_modes():
    from PIL import Image

    settings = ExportSettings(page_size="6x9", font_family="Open Sans")
    pdf_bytes, plan, _ = build_book_pdf(
        [(1, "Ch 1", _sample_export_puzzle("Ch 1"))],
        settings,
    )

    # 1. Wrong page count
    r_cnt = verify_pdf(
        pdf_bytes,
        expected_page_count=plan["total_pages"] + 2,
        expected_width_pt=plan["width_pt"],
        expected_height_pt=plan["height_pt"],
        raise_on_failure=False,
    )
    assert "page_count_matches" in r_cnt["failed_checks"]

    # 2. Wrong trim size
    r_trim = verify_pdf(
        pdf_bytes,
        expected_page_count=plan["total_pages"],
        expected_width_pt=500.0,
        expected_height_pt=700.0,
        raise_on_failure=False,
    )
    assert "trim_size_matches" in r_trim["failed_checks"]

    # 3. Missing / unembedded font (standard Helvetica without embedding)
    buf_font = io.BytesIO()
    c = canvas.Canvas(buf_font, pagesize=(432.0, 648.0))
    c.setFont("Helvetica", 12)
    c.drawString(40, 600, "Unembedded font test")
    c.rect(40, 500, 100, 50)
    c.showPage()
    c.save()
    with pytest.raises(PDFVerificationError, match="all_fonts_embedded"):
        verify_pdf(buf_font.getvalue(), expected_page_count=1, expected_width_pt=432.0, expected_height_pt=648.0)

    # 4. Injected raster image
    from app.crossword.services.export.fonts import reportlab_font_name

    reg = reportlab_font_name("Open Sans", False, False)
    buf_img = io.BytesIO()
    c_img = canvas.Canvas(buf_img, pagesize=(432.0, 648.0), initialFontName=reg, initialFontSize=10)
    c_img.setFont(reg, 10)
    c_img.drawString(40, 600, "Vector + raster")
    c_img.rect(40, 500, 50, 50)
    c_img.drawInlineImage(Image.new("RGB", (4, 4), color=(10, 20, 30)), 40, 420, 20, 20)
    c_img.showPage()
    c_img.save()
    r_img = verify_pdf(
        buf_img.getvalue(),
        expected_page_count=1,
        expected_width_pt=432.0,
        expected_height_pt=648.0,
        raise_on_failure=False,
    )
    assert "zero_raster_images" in r_img["failed_checks"]

    # 5. Transparency
    buf_alpha = io.BytesIO()
    c_al = canvas.Canvas(buf_alpha, pagesize=(432.0, 648.0), initialFontName=reg, initialFontSize=10)
    c_al.setFont(reg, 10)
    c_al.setFillAlpha(0.4)
    c_al.rect(40, 500, 100, 50, fill=1)
    c_al.showPage()
    c_al.save()
    r_al = verify_pdf(
        buf_alpha.getvalue(),
        expected_page_count=1,
        expected_width_pt=432.0,
        expected_height_pt=648.0,
        raise_on_failure=False,
    )
    assert "no_transparency" in r_al["failed_checks"]


def test_phase6_reproducibility_from_winning_seed_and_strategy(db_setup):
    client, _ = db_setup
    proj = client.post("/api/projects", json={"name": "Repro Book"}).json()
    staged = client.post(
        f"/api/projects/{proj['id']}/imports/paste",
        json={
            "text": "apple, Orchard fruit\nplanet, Orbiting world\neagle, Large raptor\ntiger, Striped feline\nriver, Flowing water\ngarden, Plant plot",
            "collection_name": "Repro Ch 1",
        },
    ).json()
    acc = client.post(
        f"/api/projects/{proj['id']}/imports/{staged['id']}/accept",
        json={"replace_existing": True},
    ).json()
    ch_id = acc["project"]["chapters"][0]["id"]

    # Trigger initial retry generation via inline auto_retry action
    act1 = client.post(
        f"/api/projects/{proj['id']}/chapters/{ch_id}/action",
        json={"action": "auto_retry"},
    )
    assert act1.status_code == 200
    p1 = act1.json()["puzzle"]
    assert p1["winning_seed"] is not None
    assert p1["winning_strategy"] is not None

    # Reproduce exact grid from recorded winning_seed & winning_strategy
    act2 = client.post(
        f"/api/projects/{proj['id']}/chapters/{ch_id}/action",
        json={"action": "reproduce"},
    )
    assert act2.status_code == 200
    p2 = act2.json()["puzzle"]
    assert p2["grid"] == p1["grid"]
    assert [(e["number"], e["direction"], e["answer"], e["row"], e["col"]) for e in p2["entries"]] == [
        (e["number"], e["direction"], e["answer"], e["row"], e["col"]) for e in p1["entries"]
    ]
    assert p2["winning_seed"] == p1["winning_seed"]
    assert p2["winning_strategy"] == p1["winning_strategy"]


def test_phase6_alembic_migrations_across_schema_states(tmp_path: Path):
    # State A: Checkpoint 2-7 legacy schema (no projects table, no display on puzzle_entries, no project_id on import_batches)
    legacy_db = tmp_path / "state_legacy.db"
    conn_a = sqlite3.connect(legacy_db)
    conn_a.executescript(
        """
        CREATE TABLE words (id INTEGER PRIMARY KEY, answer VARCHAR(64) NOT NULL, display VARCHAR(128) NOT NULL, language VARCHAR(16) NOT NULL, difficulty VARCHAR(16), category VARCHAR(128), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, UNIQUE(answer, language));
        CREATE TABLE clues (id INTEGER PRIMARY KEY, word_id INTEGER NOT NULL, text TEXT NOT NULL, difficulty VARCHAR(16), source VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE collections (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, description TEXT, language VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE collection_words (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL, word_id INTEGER NOT NULL, position INTEGER NOT NULL);
        CREATE TABLE puzzles (id INTEGER PRIMARY KEY, collection_id INTEGER, title VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL, clue_status VARCHAR(32) NOT NULL, rows INTEGER NOT NULL, cols INTEGER NOT NULL, grid JSON NOT NULL, settings JSON NOT NULL, validation JSON NOT NULL, unplaced JSON NOT NULL, stats JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE puzzle_entries (id INTEGER PRIMARY KEY, puzzle_id INTEGER NOT NULL, word_id INTEGER, clue_id INTEGER, answer VARCHAR(64) NOT NULL, number INTEGER NOT NULL, direction VARCHAR(1) NOT NULL, row INTEGER NOT NULL, col INTEGER NOT NULL, length INTEGER NOT NULL);
        CREATE TABLE jobs (id VARCHAR(64) PRIMARY KEY, type VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL, total INTEGER NOT NULL, completed INTEGER NOT NULL, failed INTEGER NOT NULL, payload JSON NOT NULL, result JSON NOT NULL, error TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE import_batches (id VARCHAR(64) PRIMARY KEY, filename VARCHAR(255), source_format VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, report JSON NOT NULL, staged_data JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        INSERT INTO words VALUES (1, 'LEGACY', 'legacy', 'en', 'easy', NULL, '2026-01-01', '2026-01-01');
        INSERT INTO clues VALUES (1, 1, 'Old clue text', 'easy', 'manual', 'approved', '2026-01-01', '2026-01-01');
        INSERT INTO collections VALUES (1, 'Legacy Set', NULL, 'en', '2026-01-01', '2026-01-01');
        INSERT INTO collection_words VALUES (1, 1, 1, 0);
        INSERT INTO puzzles VALUES (1, 1, 'Legacy Puz', 'complete', 'complete', 1, 6, '["LEGACY"]', '{}', '{"valid":true}', '[]', '{}', '2026-01-01', '2026-01-01');
        INSERT INTO puzzle_entries VALUES (1, 1, 1, 1, 'LEGACY', 1, 'A', 0, 0, 6);
        """
    )
    conn_a.commit()
    conn_a.close()

    # State B: Phase 1-2 schema (projects added, collections upgraded, before collection_words.clue_id)
    phase1_db = tmp_path / "state_phase1.db"
    conn_b = sqlite3.connect(phase1_db)
    conn_b.executescript(
        """
        CREATE TABLE words (id INTEGER PRIMARY KEY, answer VARCHAR(64) NOT NULL, display VARCHAR(128) NOT NULL, language VARCHAR(16) NOT NULL, difficulty VARCHAR(16), category VARCHAR(128), created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE clues (id INTEGER PRIMARY KEY, word_id INTEGER NOT NULL, text TEXT NOT NULL, difficulty VARCHAR(16), source VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(255) NOT NULL, project_type VARCHAR(64) NOT NULL, trim_size VARCHAR(64) NOT NULL, current_step INTEGER NOT NULL, settings JSON NOT NULL, import_metadata JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE collections (id INTEGER PRIMARY KEY, project_id INTEGER, chapter_index INTEGER NOT NULL, chapter_meta JSON NOT NULL, name VARCHAR(255) NOT NULL, description TEXT, language VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE collection_words (id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL, word_id INTEGER NOT NULL, position INTEGER NOT NULL, display VARCHAR(128), raw_word VARCHAR(255), raw_clue TEXT, cell_ref VARCHAR(64), extra_data JSON NOT NULL);
        CREATE TABLE puzzles (id INTEGER PRIMARY KEY, collection_id INTEGER, title VARCHAR(255) NOT NULL, status VARCHAR(32) NOT NULL, clue_status VARCHAR(32) NOT NULL, rows INTEGER NOT NULL, cols INTEGER NOT NULL, grid JSON NOT NULL, settings JSON NOT NULL, validation JSON NOT NULL, unplaced JSON NOT NULL, stats JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE puzzle_entries (id INTEGER PRIMARY KEY, puzzle_id INTEGER NOT NULL, word_id INTEGER, clue_id INTEGER, answer VARCHAR(64) NOT NULL, display VARCHAR(128), number INTEGER NOT NULL, direction VARCHAR(1) NOT NULL, row INTEGER NOT NULL, col INTEGER NOT NULL, length INTEGER NOT NULL);
        CREATE TABLE jobs (id VARCHAR(64) PRIMARY KEY, type VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL, total INTEGER NOT NULL, completed INTEGER NOT NULL, failed INTEGER NOT NULL, payload JSON NOT NULL, result JSON NOT NULL, error TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        CREATE TABLE import_batches (id VARCHAR(64) PRIMARY KEY, project_id INTEGER, filename VARCHAR(255), source_format VARCHAR(32) NOT NULL, status VARCHAR(32) NOT NULL, report JSON NOT NULL, staged_data JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);
        INSERT INTO projects VALUES (1, 'Phase1 Proj', 'crossword', '6x9', 1, '{}', '{}', '2026-01-01', '2026-01-01');
        INSERT INTO collections VALUES (1, 1, 0, '{}', 'Ch 1', NULL, 'en', '2026-01-01', '2026-01-01');
        INSERT INTO words VALUES (1, 'ORBIT', 'orbit', 'en', 'easy', NULL, '2026-01-01', '2026-01-01');
        INSERT INTO collection_words VALUES (1, 1, 1, 0, 'orbit', 'orbit', NULL, 'line 1', '[]');
        """
    )
    conn_b.commit()
    conn_b.close()

    # State C: Fresh DB upgraded to head cleanly
    fresh_db = tmp_path / "state_fresh.db"

    for label, db_file in (("legacy", legacy_db), ("phase1", phase1_db), ("fresh", fresh_db)):
        eng = create_db_engine(f"sqlite:///{db_file}")
        run_migrations(eng)
        insp = inspect(eng)
        with eng.connect() as c:
            rev = c.execute(sqlite_text("SELECT version_num FROM alembic_version")).scalar()
            assert rev == "0002_phase6_hardening", f"{label} expected 0002_phase6_hardening got {rev}"
            if label == "legacy":
                assert c.execute(sqlite_text("SELECT answer FROM words WHERE id=1")).scalar() == "LEGACY"
                assert c.execute(sqlite_text("SELECT answer FROM puzzle_entries WHERE id=1")).scalar() == "LEGACY"
            elif label == "phase1":
                assert c.execute(sqlite_text("SELECT name FROM projects WHERE id=1")).scalar() == "Phase1 Proj"
                assert c.execute(sqlite_text("SELECT display FROM collection_words WHERE id=1")).scalar() == "orbit"
        for tbl, idx_name in (
            ("collections", "ix_collections_project_id"),
            ("puzzles", "ix_puzzles_collection_id"),
            ("clues", "ix_clues_word_id"),
        ):
            assert any(idx["name"] == idx_name for idx in insp.get_indexes(tbl)), f"{label} missing {idx_name}"
        eng.dispose()


def sqlite_text(sql: str):
    from sqlalchemy import text

    return text(sql)


def test_phase6_100_chapter_project_end_to_end_and_job_cancellation(db_setup, capsys):
    client, SessionFactory = db_setup

    # Build 100 chapters, each using a distinct 6-word subset from a highly-crossable word pool
    word_pool = [
        "APPLE", "PLANET", "EAGLE", "TIGER", "RIVER", "GARDEN",
        "STONE", "TRAIN", "CLOUD", "OCEAN", "EARTH", "TRAIL",
    ]
    combos = list(itertools.combinations(word_pool, 6))[:100]
    blocks = []
    for ch_idx, combo in enumerate(combos, start=1):
        lines = [f"{w.lower()}, Sample educational clue for {w.lower()} in chapter {ch_idx}, easy" for w in combo]
        blocks.append("\n".join(lines))
    big_text = "\n\n".join(blocks)

    proj = client.post("/api/projects", json={"name": "Century Crossword Book", "trim_size": "6x9"}).json()
    staged = client.post(
        f"/api/projects/{proj['id']}/imports/paste",
        json={"text": big_text},
    ).json()
    assert staged["report"]["group_count"] == 100
    acc = client.post(
        f"/api/projects/{proj['id']}/imports/{staged['id']}/accept",
        json={"replace_existing": True},
    ).json()
    assert len(acc["project"]["chapters"]) == 100

    # Generate clues with FakeAIProvider in automatic mode
    fake_ai = FakeAIProvider()
    with SessionFactory() as db:
        from sqlalchemy import select
        from app.crossword.models import Word

        all_word_ids = list(db.scalars(select(Word.id)).all())
        clue_job = create_clue_generation_job(
            db,
            word_ids=all_word_ids,
            mode="automatic",
            difficulty="medium",
            verify=True,
        )
        execute_clue_generation_job(
            clue_job.id,
            SessionFactory,
            dictionary_provider=NullDictionaryProvider(),
            ai_provider=fake_ai,
        )

    # Also switch project clues mode to hybrid and generate + download via background job runner
    t0 = time.perf_counter()
    started = client.post(f"/api/projects/{proj['id']}/generate-and-download").json()
    job_info = client.get(f"/api/jobs/{started['job_id']}").json()
    elapsed = time.perf_counter() - t0

    assert job_info["status"] == "completed"
    assert "total_retries_used" in job_info["result"]
    assert "elapsed_seconds" in job_info["result"]
    print(
        f"[100-chapter benchmark] total_time_s={elapsed:.2f} "
        f"total_retries_used={job_info['result']['total_retries_used']} "
        f"total_pages={job_info['result']['page_plan']['total_pages']}"
    )

    plan = client.get(f"/api/projects/{proj['id']}/page-plan").json()
    assert plan["total_pages"] == job_info["result"]["page_plan"]["total_pages"]

    dl = client.get(f"/api/projects/{proj['id']}/download-pdf")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"
    verification = verify_pdf(
        dl.content,
        expected_page_count=plan["total_pages"],
        expected_width_pt=plan["width_pt"],
        expected_height_pt=plan["height_pt"],
    )
    assert verification["valid"] is True

    # Test cancelling a bulk/book job stops pending chapters before completion
    from app.crossword.services.bulk import create_bulk_generation_job, execute_bulk_generation_job

    ch_ids = [c["id"] for c in acc["project"]["chapters"][:10]]
    with SessionFactory() as db:
        bjob = create_bulk_generation_job(db, collection_ids=ch_ids, max_retries=1)
        bjob_id = bjob.id

    # Mark cancelled before execution (simulating user clicking Cancel mid-queue)
    cancel_resp = client.post(f"/api/jobs/{bjob_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    execute_bulk_generation_job(bjob_id, SessionFactory, use_process_pool=False)
    after_cancel = client.get(f"/api/jobs/{bjob_id}").json()
    assert after_cancel["status"] == "cancelled"
    assert after_cancel["completed"] == 0


def test_no_api_key_leak_in_errors_or_saved_project(db_setup, monkeypatch):
    client, _ = db_setup
    fake_secret = "sk-ant-secret-key-should-never-leak-98765"
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_secret)

    proj = client.post("/api/projects", json={"name": "Security Check Book"}).json()
    staged = client.post(
        f"/api/projects/{proj['id']}/imports/paste",
        json={"text": "apple, Fruit\nplanet, World", "collection_name": "SecCh"},
    ).json()
    client.post(
        f"/api/projects/{proj['id']}/imports/{staged['id']}/accept",
        json={"replace_existing": True},
    )

    exported = client.get(f"/api/projects/{proj['id']}/export-json").text
    assert fake_secret not in exported

    # Trigger an intentional HTTP error and inspect response body
    err_resp = client.get("/api/projects/999999")
    assert err_resp.status_code == 404
    assert fake_secret not in err_resp.text

    # Confirm failing AI provider exception never stores raw API key in Job.error
    from app.crossword.services.clues.ai import AIProvider

    class _ExplodingAI(AIProvider):
        name = "exploding"

        def generate_batch(self, items, difficulty="medium", age_group="general"):
            raise RuntimeError(f"Upstream call failed using key={fake_secret}")

        def verify_clue(self, clue, length):
            return None

    _, SessionFactory = db_setup
    from sqlalchemy import select
    from app.crossword.models import Word

    with SessionFactory() as db:
        wids = list(db.scalars(select(Word.id)).all())
        cjob = create_clue_generation_job(db, word_ids=wids, mode="automatic")
        cjob_id = cjob.id

    execute_clue_generation_job(
        cjob_id,
        SessionFactory,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=_ExplodingAI(),
    )
    job_out = client.get(f"/api/jobs/{cjob_id}").json()
    assert job_out["status"] == "failed"
    assert fake_secret not in (job_out.get("error") or "")
    assert "[REDACTED]" in (job_out.get("error") or "")

