"""Phase 1 tests: Project model & library, autosave, JSON roundtrip, chapter import, enumeration & min_len=3."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory
from app.main import app
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from app.crossword.services.export.renderers import render_svg
from app.crossword.services.export.settings import ExportSettings


@pytest.fixture()
def client_and_session(tmp_path: Path):
    db_path = tmp_path / "phase1_test.db"
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


def test_project_library_crud_autosave_and_json_roundtrip(client_and_session):
    client, _ = client_and_session

    # Create project
    create_res = client.post(
        "/api/projects",
        json={
            "name": "Nature Book",
            "project_type": "crossword",
            "trim_size": "6x9",
            "settings": {"words_per_chapter": 3},
        },
    )
    assert create_res.status_code == 201, create_res.text
    proj = create_res.json()
    pid = proj["id"]
    assert proj["name"] == "Nature Book"
    assert proj["project_type"] == "crossword"
    assert proj["trim_size"] == "6x9"
    assert proj["settings"]["grid"]["min_word_length"] == 3
    assert proj["settings"]["enumeration_display"] == "formatted"

    # Listed in project library
    lib = client.get("/api/projects").json()
    assert len(lib) == 1
    assert lib[0]["id"] == pid

    # Autosave partial settings via PATCH (deep merge preserves existing nested settings)
    patch_res = client.patch(
        f"/api/projects/{pid}",
        json={
            "trim_size": "8x10",
            "current_step": 3,
            "settings": {
                "enumeration_display": "formatted",
                "appearance": {"capital_letters": False},
            },
        },
    )
    assert patch_res.status_code == 200
    patched = patch_res.json()
    assert patched["trim_size"] == "8x10"
    assert patched["current_step"] == 3
    assert patched["settings"]["trim"]["preset"] == "8x10"
    assert patched["settings"]["appearance"]["capital_letters"] is False
    assert patched["settings"]["words_per_chapter"] == 3  # preserved
    assert patched["autosaved_at"] is not None

    # Import multi-word chapter with extra column
    csv_bytes = (
        "Word,Clue,Notes\n"
        "ice cream,Frozen sweet treat,Dessert note\n"
        "apple pie,Baked pastry,Classic dish\n"
        "pear,Orchard fruit,Snack\n"
    ).encode("utf-8")
    staged = client.post(
        f"/api/projects/{pid}/imports",
        files={"file": ("ch1.csv", csv_bytes, "text/csv")},
    ).json()
    accepted = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept").json()
    proj_after = accepted["project"]
    assert proj_after["chapter_count"] == 1
    ch = proj_after["chapters"][0]
    assert ch["status"] == "Ready"
    assert ch["word_count_label"] == "Expected 3, found 3"
    assert ch["words"][0]["display"] == "ice cream"
    assert ch["words"][0]["enumeration"] == "(3,5)"
    assert ch["words"][0]["cell_ref"] == "line 2, col 1"
    assert len(ch["words"][0]["extra_data"]) == 1
    assert ch["words"][0]["extra_data"][0]["value"] == "Dessert note"

    # Generate puzzle for chapter
    puz = client.post(
        "/api/puzzles/generate",
        json={"collection_id": ch["id"], "title": "Chapter 1"},
    ).json()
    assert puz["validation"]["valid"] is True

    # Export JSON and restore into a brand new project record
    exported = client.get(f"/api/projects/{pid}/export-json").json()
    assert exported["schema_version"] == 1
    assert exported["name"] == "Nature Book"
    assert len(exported["chapters"]) == 1
    assert len(exported["chapters"][0]["puzzles"]) == 1

    restored_res = client.post("/api/projects/import-json", json=exported)
    assert restored_res.status_code == 201, restored_res.text
    restored = restored_res.json()
    assert restored["id"] != pid
    assert restored["name"] == "Nature Book"
    assert restored["trim_size"] == "8x10"
    assert restored["settings"]["appearance"]["capital_letters"] is False
    r_ch = restored["chapters"][0]
    assert r_ch["words"][0]["display"] == "ice cream"
    assert r_ch["words"][0]["raw_word"] == "ice cream"
    assert r_ch["words"][0]["cell_ref"] == "line 2, col 1"
    assert r_ch["words"][0]["enumeration"] == "(3,5)"
    assert r_ch["words"][0]["extra_data"][0]["value"] == "Dessert note"
    assert r_ch["puzzle_id"] is not None

    # Delete original project cleanly
    del_res = client.delete(f"/api/projects/{pid}")
    assert del_res.status_code == 204
    assert len(client.get("/api/projects").json()) == 1


def test_chapter_import_blank_rows_runs_whitespace_and_spaces_in_words(client_and_session):
    client, _ = client_and_session
    pid = client.post("/api/projects", json={"name": "Multi Chapter"}).json()["id"]

    # Leading whitespace lines, spaces inside words, runs of blank & whitespace-only lines, trailing blanks
    text = (
        "\n"
        "   \n"
        "ice cream\n"
        "hot dog\n"
        "apple pie\n"
        "\n"
        "   \n"
        "\t  \n"
        "New York\n"
        "Los Angeles\n"
        "San Jose\n"
        "   \n"
        "\n"
    )
    staged = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": text},
    )
    assert staged.status_code == 200, staged.text
    report = staged.json()["report"]

    # Run of blank/whitespace lines counted once -> exactly 2 chapters, no empty chapters
    assert report["group_count"] == 2
    assert report["valid_count"] == 6
    ch1, ch2 = report["groups"]
    assert ch1["name"] == "Chapter 1"
    assert ch2["name"] == "Chapter 2"
    assert [w["answer"] for w in ch1["words"]] == ["ICECREAM", "HOTDOG", "APPLEPIE"]
    assert [w["display"] for w in ch1["words"]] == ["ice cream", "hot dog", "apple pie"]
    assert [w["enumeration"] for w in ch1["words"]] == ["(3,5)", "(3,3)", "(5,3)"]
    assert [w["answer"] for w in ch2["words"]] == ["NEWYORK", "LOSANGELES", "SANJOSE"]
    assert ch1["words"][0]["cell_ref"] == "line 3, col 1"
    assert ch2["words"][0]["cell_ref"] == "line 9, col 1"


def test_excel_multisheet_order_cell_refs_skipped_headers_and_extra_columns(client_and_session):
    client, _ = client_and_session
    pid = client.post("/api/projects", json={"name": "Workbook Book"}).json()["id"]

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Animals"
    ws1.append(["Word", "Clue", "AuthorNote", "PageTag"])
    ws1.append(["  sea lion  ", "Barking marine mammal", "Keep easy", "p1"])
    ws1.append(["tiger", "Striped big cat", "", ""])
    ws1.append(["cat", "Household feline", "", ""])

    ws2 = wb.create_sheet("Space")
    ws2.append(["Word", "Clue"])
    ws2.append(["planet", "World orbiting a star"])
    ws2.append(["comet", "Icy solar traveler"])
    ws2.append(["orbit", "Curved path"])
    ws2.append(["   ", None])
    ws2.append(["star", "Luminous plasma sphere"])
    ws2.append(["moon", "Natural satellite"])
    ws2.append(["mars", "Red planet"])

    ws3 = wb.create_sheet("Plants")
    ws3.append(["Word", "Clue"])
    ws3.append(["rose", "Thorny flower"])
    ws3.append(["oak", "Acorn tree"])
    ws3.append(["fern", "Shade frond"])

    buf = io.BytesIO()
    wb.save(buf)

    res = client.post(
        f"/api/projects/{pid}/imports",
        files={
            "file": (
                "book.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 200, res.text
    report = res.json()["report"]

    # Sheets imported in order; Space has 2 blank-row-separated blocks
    assert [g["name"] for g in report["groups"]] == [
        "Animals",
        "Space - Chapter 1",
        "Space - Chapter 2",
        "Plants",
    ]
    # Header rows skipped with notes
    assert report["skipped_header_count"] == 3
    assert any("Animals!A1" in h["note"] for h in report["skipped_headers"])
    assert any("Space!A1" in h["note"] for h in report["skipped_headers"])
    assert any("Plants!A1" in h["note"] for h in report["skipped_headers"])

    # Raw text and Excel cell references preserved
    first_word = report["groups"][0]["words"][0]
    assert first_word["raw"] == "  sea lion  "
    assert first_word["display"] == "sea lion"
    assert first_word["answer"] == "SEALION"
    assert first_word["cell_ref"] == "Animals!A2"

    # Extra column data outside Word/Clue reported and preserved, never dropped
    assert report["extra_column_count"] == 2
    refs = {ex["cell_ref"]: ex["value"] for ex in report["extra_columns"]}
    assert refs == {"Animals!C2": "Keep easy", "Animals!D2": "p1"}
    assert [e["value"] for e in first_word["extra_data"]] == ["Keep easy", "p1"]


def test_preview_before_accept_per_chapter_status_and_expected_found(client_and_session):
    client, _ = client_and_session
    pid = client.post(
        "/api/projects",
        json={
            "name": "Status Check Book",
            "settings": {
                "words_per_chapter": 3,
                "grid": {"mode": "custom", "rows": 6, "cols": 6, "min_word_length": 3},
            },
        },
    ).json()["id"]

    csv_text = (
        "Chapter,Word,Clue\n"
        "Ch1 Ready,cat,Small feline\n"
        "Ch1 Ready,car,Four-wheeled vehicle\n"
        "Ch1 Ready,tar,Dark road pitch\n"
        "Ch2 Missing,apple,Orchard fruit\n"
        "Ch2 Missing,pear,\n"
        "Ch3 Wont Fit,cat,Small feline\n"
        "Ch3 Wont Fit,dog,Loyal canine\n"
        "Ch3 Wont Fit,extraordinary,Remarkable and unusual\n"
        "Ch4 Invalid,r2d2,Star Wars droid\n"
        "Ch4 Invalid,cat,Small feline\n"
    )
    staged_res = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": csv_text},
    )
    assert staged_res.status_code == 200, staged_res.text
    staged = staged_res.json()
    chapters = staged["report"]["groups"]
    assert len(chapters) == 4

    by_name = {c["name"]: c for c in chapters}
    assert by_name["Ch1 Ready"]["status"] == "Ready"
    assert by_name["Ch1 Ready"]["word_count_label"] == "Expected 3, found 3"
    assert by_name["Ch1 Ready"]["word_count_matches"] is True

    assert by_name["Ch2 Missing"]["status"] == "Missing clues"
    assert by_name["Ch2 Missing"]["word_count_label"] == "Expected 3, found 2"
    assert by_name["Ch2 Missing"]["word_count_matches"] is False
    assert by_name["Ch2 Missing"]["missing_clues"] == ["PEAR"]

    assert by_name["Ch3 Wont Fit"]["status"] == "Words won't fit"
    assert by_name["Ch3 Wont Fit"]["word_count_label"] == "Expected 3, found 3"
    assert any(u["answer"] == "EXTRAORDINARY" for u in by_name["Ch3 Wont Fit"]["unplaced_words"])

    assert by_name["Ch4 Invalid"]["status"] == "Invalid"
    assert by_name["Ch4 Invalid"]["invalid_count"] == 1
    assert by_name["Ch4 Invalid"]["invalid"][0]["raw"] == "r2d2"

    # Nothing committed to the project before Accept
    before_accept = client.get(f"/api/projects/{pid}").json()
    assert before_accept["chapter_count"] == 0

    # Accept commits all 4 chapters and preserves statuses
    accept_res = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept")
    assert accept_res.status_code == 200, accept_res.text
    proj_after = accept_res.json()["project"]
    assert proj_after["chapter_count"] == 4
    saved_by_name = {c["name"]: c for c in proj_after["chapters"]}
    assert saved_by_name["Ch1 Ready"]["status"] == "Ready"
    assert saved_by_name["Ch2 Missing"]["status"] == "Missing clues"
    assert saved_by_name["Ch3 Wont Fit"]["status"] == "Words won't fit"
    assert saved_by_name["Ch4 Invalid"]["status"] == "Invalid"


def test_enumeration_display_in_clue_export():
    puzzle = ExportPuzzleData(
        title="Enum Test",
        rows=8,
        cols=8,
        grid=["ICECREAM"] + ["########"] * 7,
        entries=[
            ExportEntry(
                number=1,
                direction="A",
                row=0,
                col=0,
                answer="ICECREAM",
                clue="Frozen sweet treat",
                display="ice cream",
            ),
            ExportEntry(
                number=2,
                direction="D",
                row=0,
                col=0,
                answer="FOURLEAF",
                clue="Lucky clover kind",
                display="four-leaf",
            ),
        ],
    )

    def _texts(style: str) -> list[str]:
        pages = build_export_pages(
            puzzle,
            "clues",
            ExportSettings(page_size="letter", show_clue_lengths=True, enumeration_display=style),
        )
        root = ET.fromstring(render_svg(pages[0]))
        return [el.text or "" for el in root.iter() if el.tag.endswith("text")]

    fmt_texts = " ".join(_texts("formatted"))
    assert "Frozen sweet treat (3,5)" in fmt_texts
    assert "Lucky clover kind (4-4)" in fmt_texts

    tot_texts = " ".join(_texts("total"))
    assert "Frozen sweet treat (8)" in tot_texts
    assert "Lucky clover kind (8)" in tot_texts

    none_texts = " ".join(_texts("none"))
    assert "(3,5)" not in none_texts
    assert "(4-4)" not in none_texts
    assert "(8)" not in none_texts


def test_min_word_length_default_3_and_configurable(client_and_session):
    client, _ = client_and_session
    pid = client.post("/api/projects", json={"name": "Length Rules"}).json()["id"]

    # Default min_word_length = 3 rejects 'ox' and 'it'
    res_default = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": "ox, Bovine animal\nit, Pronoun\ncat, Small feline\n"},
    ).json()
    rep = res_default["report"]
    assert rep["min_word_length"] == 3
    assert rep["valid_count"] == 1
    assert rep["invalid_count"] == 2
    assert all("minimum length of 3" in inv["reason"] for inv in rep["invalid"])

    # Update project setting to min_word_length = 2 -> both 'ox' and 'it' accepted
    client.patch(
        f"/api/projects/{pid}",
        json={"settings": {"grid": {"min_word_length": 2}}},
    )
    res_two = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": "ox, Bovine animal\nit, Pronoun\ncat, Small feline\n"},
    ).json()
    assert res_two["report"]["min_word_length"] == 2
    assert res_two["report"]["valid_count"] == 3
    assert res_two["report"]["invalid_count"] == 0


def test_variable_words_per_chapter_default(client_and_session):
    client, _ = client_and_session
    proj = client.post("/api/projects", json={"name": "Mixed Lengths Book"}).json()
    pid = proj["id"]
    assert proj["settings"]["words_per_chapter"] is None

    # Chapter 1 has 3 words, Chapter 2 has 5 words — both should match cleanly without a mismatch flag
    text = (
        "cat, Feline\ndog, Canine\nowl, Night bird\n\n"
        "apple, Orchard fruit\ngrape, Vine fruit\npeach, Fuzzy fruit\nmango, Tropical fruit\nplum, Purple fruit\n"
    )
    staged = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": text},
    ).json()
    groups = staged["report"]["chapters"]
    assert len(groups) == 2
    assert groups[0]["word_count_label"] == "Found 3"
    assert groups[0]["word_count_matches"] is True
    assert groups[1]["word_count_label"] == "Found 5"
    assert groups[1]["word_count_matches"] is True

    # Switching to a fixed count works and switching back to None clears it
    fixed_proj = client.patch(
        f"/api/projects/{pid}",
        json={"settings": {"words_per_chapter": 4}},
    ).json()
    assert fixed_proj["settings"]["words_per_chapter"] == 4

    staged_fixed = client.post(
        f"/api/projects/{pid}/imports/paste",
        json={"text": text},
    ).json()
    assert staged_fixed["report"]["chapters"][0]["word_count_label"] == "Expected 4, found 3"
    assert staged_fixed["report"]["chapters"][0]["word_count_matches"] is False

    var_proj = client.patch(
        f"/api/projects/{pid}",
        json={"settings": {"words_per_chapter": None}},
    ).json()
    assert var_proj["settings"]["words_per_chapter"] is None

