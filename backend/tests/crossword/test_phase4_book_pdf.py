"""Phase 4 tests: page plan calculator, build_book_pdf, bookmarks, verify_pdf, Open Sans & background job."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory
from app.main import app
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData
from app.crossword.services.export.settings import ExportSettings


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "phase4_test.db"
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


def _sample_export_puzzle(title: str, entry_count: int = 3) -> ExportPuzzleData:
    if entry_count <= 3:
        entries = [
            ExportEntry(number=1, direction="A", row=0, col=0, answer="CAT", clue="Small feline", display="cat"),
            ExportEntry(number=1, direction="D", row=0, col=0, answer="CAR", clue="Road vehicle", display="car"),
            ExportEntry(number=2, direction="D", row=0, col=2, answer="TAR", clue="Dark road pitch", display="tar"),
        ][:entry_count]
    else:
        entries = [
            ExportEntry(
                number=i,
                direction="A" if i % 2 else "D",
                row=0,
                col=0,
                answer="PLANET",
                clue=f"Clue #{i} with enough explanatory text to wrap cleanly across multiple lines in the print layout.",
                display="planet",
            )
            for i in range(1, entry_count + 1)
        ]
    return ExportPuzzleData(
        title=title,
        rows=3,
        cols=3,
        grid=["CAT", "A#A", "R#R"],
        entries=entries,
    )


def _flatten_outline_titles(outline) -> list[str]:
    titles: list[str] = []
    for item in outline:
        if isinstance(item, list):
            titles.extend(_flatten_outline_titles(item))
        else:
            title = getattr(item, "title", None) or (item.get("/Title") if isinstance(item, dict) else None)
            if title:
                titles.append(str(title))
    return titles


def test_page_plan_matches_built_pdf_odd_even_and_right_hand_start():
    from app.crossword.services.export.book import build_book_pdf, compute_book_page_plan

    settings = ExportSettings(page_size="6x9", font_family="Open Sans")

    # Case 1: 2 puzzle pages + 1 solution page = 3 (odd) -> +1 trailing blank = 4
    ch_two = [
        (1, "Chapter 1", _sample_export_puzzle("Chapter 1")),
        (2, "Chapter 2", _sample_export_puzzle("Chapter 2")),
    ]
    plan_odd = compute_book_page_plan(ch_two, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=False)
    assert plan_odd["puzzle_pages"] == 2
    assert plan_odd["solution_pages"] == 1
    assert plan_odd["front_matter_blank_pages"] == 0
    assert plan_odd["trailing_blank_pages"] == 1
    assert plan_odd["total_pages"] == 4

    pdf_odd, used_plan_odd, ver_odd = build_book_pdf(
        ch_two, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=False
    )
    assert used_plan_odd == plan_odd
    assert ver_odd["valid"] is True
    reader_odd = PdfReader(io.BytesIO(pdf_odd))
    assert len(reader_odd.pages) == plan_odd["total_pages"]
    assert _flatten_outline_titles(reader_odd.outline) == ["Chapter 1", "Chapter 2", "Solutions"]

    # Case 2: 3 puzzle pages + 1 solution page = 4 (even) -> +0 trailing blank = 4
    ch_three = ch_two + [(3, "Chapter 3", _sample_export_puzzle("Chapter 3"))]
    plan_even = compute_book_page_plan(ch_three, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=False)
    assert plan_even["puzzle_pages"] == 3
    assert plan_even["solution_pages"] == 1
    assert plan_even["trailing_blank_pages"] == 0
    assert plan_even["total_pages"] == 4
    pdf_even, _, _ = build_book_pdf(ch_three, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=False)
    assert len(PdfReader(io.BytesIO(pdf_even)).pages) == 4

    # Case 3: start_puzzles_on_right_hand_page=True adds 1 front-matter blank page
    # 1 front blank + 2 puzzles + 1 solution = 4 -> 0 trailing blank
    plan_rh = compute_book_page_plan(ch_two, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=True)
    assert plan_rh["front_matter_blank_pages"] == 1
    assert plan_rh["trailing_blank_pages"] == 0
    assert plan_rh["total_pages"] == 4
    pdf_rh, _, _ = build_book_pdf(ch_two, settings, solutions_per_page=4, start_puzzles_on_right_hand_page=True)
    assert len(PdfReader(io.BytesIO(pdf_rh)).pages) == 4


def test_multipage_clue_list_page_plan_and_pdf_match():
    from app.crossword.services.export.book import build_book_pdf, compute_book_page_plan

    settings = ExportSettings(page_size="6x9", font_family="Open Sans")
    chapters = [
        (1, "Long Chapter", _sample_export_puzzle("Long Chapter", entry_count=60)),
    ]
    plan = compute_book_page_plan(chapters, settings, solutions_per_page=1)
    assert plan["chapters"][0]["puzzle_pages"] >= 2
    assert plan["puzzle_pages"] == plan["chapters"][0]["puzzle_pages"]

    pdf_bytes, used_plan, ver = build_book_pdf(chapters, settings, solutions_per_page=1)
    assert ver["valid"] is True
    assert len(PdfReader(io.BytesIO(pdf_bytes)).pages) == used_plan["total_pages"]


def test_no_partial_books_and_require_all_clues_approved(db_setup):
    client, SessionLocal = db_setup
    pid = client.post("/api/projects", json={"name": "Strict Book"}).json()["id"]

    # Chapter 1 is ready; Chapter 2 has ZZZ which cannot place -> Needs attention
    paste_text = (
        "Chapter,Word,Clue\n"
        "Ch1,cat,Small feline\n"
        "Ch1,car,Road vehicle\n"
        "Ch1,tar,Road pitch\n"
        "Ch2,cat,Small feline\n"
        "Ch2,car,Road vehicle\n"
        "Ch2,zzz,Sleeping sound\n"
    )
    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    proj = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept").json()["project"]
    ch1_id, ch2_id = [c["id"] for c in proj["chapters"]]

    # Generate puzzles -> Ch2 is Needs attention
    client.post("/api/puzzles/generate", json={"collection_id": ch1_id})
    client.post("/api/puzzles/generate", json={"collection_id": ch2_id})

    # Refuses partial book
    dl_res = client.get(f"/api/projects/{pid}/download-pdf")
    assert dl_res.status_code == 409
    assert "Ch2" in str(dl_res.json()["detail"])

    # Now create a project with a dictionary/AI needs_review clue using a fresh word ('art')
    pid2 = client.post("/api/projects", json={"name": "Review Setting Book"}).json()["id"]
    staged2 = client.post(
        f"/api/projects/{pid2}/imports/paste",
        json={"text": "Word,Clue\ncat,Feline\ncar,Vehicle\nart,\n"},
    ).json()
    proj2 = client.post(f"/api/projects/{pid2}/imports/{staged2['id']}/accept").json()["project"]
    c2_id = proj2["chapters"][0]["id"]

    # Create a needs_review clue for ART
    from app.crossword.services.clues.ai import FakeAIProvider
    from app.crossword.services.clues.dictionary import NullDictionaryProvider
    from app.crossword.services.clues.service import create_clue_generation_job, execute_clue_generation_job

    with SessionLocal() as db:
        cjob = create_clue_generation_job(db, collection_id=c2_id, mode="hybrid", difficulty="medium", verify=False)
        cjob_id = cjob.id
    execute_clue_generation_job(
        cjob_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(verify_succeeds=False),
    )
    client.post("/api/puzzles/generate", json={"collection_id": c2_id})

    # Default: require_all_clues_approved=False -> warning only, build allowed
    p2_default = client.get(f"/api/projects/{pid2}").json()
    assert p2_default["can_generate_and_download"] is True
    assert any(w["type"] == "unapproved_clues" for w in p2_default["warnings"])
    ok_pdf = client.get(f"/api/projects/{pid2}/download-pdf")
    assert ok_pdf.status_code == 200
    assert ok_pdf.content.startswith(b"%PDF-")

    # Enable require_all_clues_approved=True -> becomes a blocker, build refused
    client.patch(
        f"/api/projects/{pid2}",
        json={"settings": {"clues": {"require_all_clues_approved": True}}},
    )
    p2_strict = client.get(f"/api/projects/{pid2}").json()
    assert p2_strict["can_generate_and_download"] is False
    assert any(b["type"] == "unapproved_clues" and "ART" in b["words"] for b in p2_strict["blocking_issues"])
    blocked_pdf = client.get(f"/api/projects/{pid2}/download-pdf")
    assert blocked_pdf.status_code == 409


def test_verify_pdf_fails_on_raster_image_missing_font_wrong_page_count_and_transparency():
    from app.crossword.services.export.book import build_book_pdf
    from app.crossword.services.export.verifier import PDFVerificationError, verify_pdf

    settings = ExportSettings(page_size="6x9", font_family="Open Sans")
    chapters = [
        (1, "Ch 1", _sample_export_puzzle("Ch 1")),
        (2, "Ch 2", _sample_export_puzzle("Ch 2")),
    ]
    valid_pdf, plan, ver = build_book_pdf(chapters, settings, solutions_per_page=4)
    assert ver["valid"] is True
    assert all(ver["checks"].values())

    # 1. Wrong page count
    with pytest.raises(PDFVerificationError, match="page_count_matches"):
        verify_pdf(valid_pdf, expected_page_count=99, expected_width_pt=432.0, expected_height_pt=648.0)

    # 2. Wrong trim size
    with pytest.raises(PDFVerificationError, match="trim_size_matches"):
        verify_pdf(valid_pdf, expected_page_count=plan["total_pages"], expected_width_pt=612.0, expected_height_pt=792.0)

    # 3. Injected raster image
    buf_img = io.BytesIO()
    c_img = canvas.Canvas(buf_img, pagesize=(432.0, 648.0))
    c_img.rect(50, 50, 100, 100, stroke=1, fill=0)
    c_img.drawInlineImage(Image.new("RGB", (8, 8), "red"), 60, 60, width=20, height=20)
    c_img.save()
    with pytest.raises(PDFVerificationError, match="zero_raster_images"):
        verify_pdf(buf_img.getvalue(), expected_page_count=1, expected_width_pt=432.0, expected_height_pt=648.0)

    # 4. Unembedded standard font (Helvetica)
    buf_font = io.BytesIO()
    c_font = canvas.Canvas(buf_font, pagesize=(432.0, 648.0))
    c_font.rect(50, 50, 100, 100, stroke=1, fill=0)
    c_font.setFont("Helvetica", 12)
    c_font.drawString(60, 600, "Unembedded font")
    c_font.save()
    with pytest.raises(PDFVerificationError, match="all_fonts_embedded"):
        verify_pdf(buf_font.getvalue(), expected_page_count=1, expected_width_pt=432.0, expected_height_pt=648.0)

    # 5. Transparency
    buf_alpha = io.BytesIO()
    c_alpha = canvas.Canvas(buf_alpha, pagesize=(432.0, 648.0))
    c_alpha.setFillAlpha(0.5)
    c_alpha.rect(50, 50, 100, 100, stroke=1, fill=1)
    c_alpha.save()
    with pytest.raises(PDFVerificationError, match="no_transparency"):
        verify_pdf(buf_alpha.getvalue(), expected_page_count=1, expected_width_pt=432.0, expected_height_pt=648.0)


def test_open_sans_embedded_and_only_embeddable_fonts_offered(db_setup):
    client, _ = db_setup
    from app.crossword.services.export.book import build_book_pdf
    from app.crossword.services.export.fonts import _BUNDLED_FONT_DIR, list_available_fonts

    assert (_BUNDLED_FONT_DIR / "OFL.txt").exists()

    fonts = list_available_fonts()
    names = {f["family"] for f in fonts}
    assert "Open Sans" in names
    assert "Vera" in names
    assert "Arial" not in names

    api_fonts = client.get("/api/export/fonts").json()
    assert {f["family"] for f in api_fonts} == names

    settings = ExportSettings(page_size="6x9", font_family="Open Sans")
    pdf_bytes, _, ver = build_book_pdf(
        [(1, "Ch 1", _sample_export_puzzle("Ch 1")), (2, "Ch 2", _sample_export_puzzle("Ch 2"))],
        settings,
    )
    assert ver["checks"]["all_fonts_embedded"] is True
    assert b"OpenSans" in pdf_bytes


def test_generate_and_download_background_job_cancel_and_retry_failed_chapters(db_setup):
    client, SessionLocal = db_setup
    pid = client.post("/api/projects", json={"name": "My Book"}).json()["id"]
    paste_text = (
        "Chapter,Word,Clue\n"
        "Chapter 1,cat,Small feline\n"
        "Chapter 1,car,Road vehicle\n"
        "Chapter 1,tar,Road pitch\n"
        "Chapter 2,apple,Orchard fruit\n"
        "Chapter 2,planet,Orbiting body\n"
        "Chapter 2,pear,Bell fruit\n"
    )
    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept")

    # Run background Generate & Download job
    start_res = client.post(f"/api/projects/{pid}/generate-and-download")
    assert start_res.status_code == 202, start_res.text
    job_info = start_res.json()
    assert "job_id" in job_info
    assert "remaining" in job_info

    job = client.get(f"/api/jobs/{job_info['job_id']}").json()
    assert job["status"] == "completed"
    assert job["remaining"] == 0
    assert job["result"]["verification"]["valid"] is True
    assert job["result"]["page_plan"]["total_pages"] == 4

    pdf_res = client.get(f"/api/projects/{pid}/download-pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.content.startswith(b"%PDF-")
    assert "my_book.pdf" in pdf_res.headers.get("content-disposition", "")

    # Cancel job endpoint works cleanly on an active/pending job
    from app.crossword.models import Job

    with SessionLocal() as db:
        pending_job = Job(
            id="cancel_test_job",
            type="book_generate_and_download",
            status="running",
            total=10,
            completed=3,
            failed=0,
            payload={},
            result={},
        )
        db.add(pending_job)
        db.commit()
    cancel_res = client.post("/api/jobs/cancel_test_job/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["remaining"] == 7

    # Retry failed chapters endpoint
    pid2 = client.post("/api/projects", json={"name": "Retry Book"}).json()["id"]
    staged2 = client.post(
        f"/api/projects/{pid2}/imports/paste",
        json={"text": "Word,Clue\ncat,Feline\ncar,Vehicle\nzzz,Sleep sound\n"},
    ).json()
    proj2 = client.post(f"/api/projects/{pid2}/imports/{staged2['id']}/accept").json()["project"]
    cid2 = proj2["chapters"][0]["id"]
    client.post("/api/puzzles/generate", json={"collection_id": cid2})

    retry_res = client.post(f"/api/projects/{pid2}/retry-failed-chapters")
    assert retry_res.status_code == 200
    assert retry_res.json()["retried_chapters"] == 1


def test_50_chapter_book_ends_in_verified_pdf(db_setup):
    client, _ = db_setup
    pid = client.post(
        "/api/projects",
        json={
            "name": "Fifty Chapter Book",
            "trim_size": "6x9",
            "settings": {
                "solution": {"per_page": 4},
                "appearance": {"font_family": "Open Sans"},
            },
        },
    ).json()["id"]

    lines = ["Chapter,Word,Clue"]
    for i in range(1, 51):
        lines.append(f"Chapter {i},cat,Small feline {i}")
        lines.append(f"Chapter {i},car,Road vehicle {i}")
        lines.append(f"Chapter {i},tar,Dark road pitch {i}")
        lines.append(f"Chapter {i},art,Creative work {i}")
    paste_text = "\n".join(lines)

    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept")

    start_res = client.post(f"/api/projects/{pid}/generate-and-download")
    assert start_res.status_code == 202, start_res.text
    job = client.get(f"/api/jobs/{start_res.json()['job_id']}").json()
    assert job["status"] == "completed"
    assert job["result"]["verification"]["valid"] is True

    # 50 puzzle pages + 13 solution pages (ceil(50/4)) = 63 (odd) -> +1 blank = 64
    plan = job["result"]["page_plan"]
    assert plan["puzzle_pages"] == 50
    assert plan["solution_pages"] == 13
    assert plan["trailing_blank_pages"] == 1
    assert plan["total_pages"] == 64

    dl = client.get(f"/api/projects/{pid}/download-pdf")
    assert dl.status_code == 200
    reader = PdfReader(io.BytesIO(dl.content))
    assert len(reader.pages) == 64
    outlines = _flatten_outline_titles(reader.outline)
    assert len(outlines) == 51
    assert outlines[0] == "Chapter 1"
    assert outlines[49] == "Chapter 50"
    assert outlines[-1] == "Solutions"
