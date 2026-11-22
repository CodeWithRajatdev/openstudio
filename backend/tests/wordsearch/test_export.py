import io
import time

import pypdf
import pytest

from app.wordsearch.engine import Difficulty, PuzzleConfig, difficulty_preset, generate_puzzle
from app.wordsearch.engine.bulk import generate_chapters
from app.wordsearch.export import (PdfOptions, build_book_pdf, build_pdf, inspect_pdf_fonts,
                        inspect_pdf_vectors, pdf_filename, verify_pdf)
from app.wordsearch.render import PageLayout, page_plan
from app.wordsearch.render.fonts import available as available_fonts

FRUIT = ["APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON", "PEACH", "CHERRY"]


def chapters(n=5):
    return [(f"Chapter {i + 1}: Fruits", [f"{w}" for w in FRUIT]) for i in range(n)]


@pytest.fixture(scope="module")
def result():
    cfg = difficulty_preset(Difficulty.HARD)
    return generate_chapters(chapters(5), cfg, base_seed=100), cfg


def test_bulk_isolates_failures_and_reports_progress():
    seen = []
    ch = chapters(2) + [("Bad", ["CAT", "???"]), ("Good", ["DOG", "FOX"])]
    res = generate_chapters(ch, PuzzleConfig(), progress=lambda a, b: seen.append((a, b)))
    assert [c.ok for c in res.chapters] == [True, True, False, True]
    assert res.failed[0].error.failed_words == ["???"]
    assert seen[-1] == (4, 4)


def test_bulk_cancel_and_seeds_reproducible():
    res = generate_chapters(chapters(4), PuzzleConfig(), cancelled=lambda: False)
    again = generate_chapters(chapters(4), PuzzleConfig(), cancelled=lambda: False)
    assert [c.puzzle.grid for c in res.chapters] == [c.puzzle.grid for c in again.chapters]
    stopped = generate_chapters(chapters(4), PuzzleConfig(), cancelled=lambda: True)
    assert stopped.chapters == []


def test_pdf_pages_size_and_structure(result):
    res, _ = result
    items = [(c.puzzle, c.title) for c in res.succeeded]
    layout = PageLayout()
    pdf, info = build_pdf(items, layout, PdfOptions(per_page_answers=2))
    r = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(r.pages) == 5 + 3 == info["total_pages"]
    assert info["answers_start_page"] == 6
    box = r.pages[0].mediabox
    assert abs(float(box.width) - 215.9 / 25.4 * 72) < 0.5
    assert abs(float(box.height) - 279.4 / 25.4 * 72) < 0.5
    titles = [o.title for o in r.outline]
    assert len(titles) == 5 + 1
    assert titles[-1] == "Solutions"
    text = r.pages[0].extract_text()
    assert "Chapter 1: Fruits" in text and "APPLE" in text
    assert "Answer Key" in r.pages[5].extract_text()


def test_pdf_adds_blank_page_when_total_is_odd(result):
    res, _ = result
    items = [(c.puzzle, c.title) for c in res.succeeded[:4]]
    # 4 puzzle pages + 1 solution page (4 per page) = 5 -> +1 blank = 6 total pages
    pdf, info = build_pdf(items, PageLayout(), PdfOptions(per_page_answers=4))
    r = pypdf.PdfReader(io.BytesIO(pdf))
    assert info["puzzle_pages"] == 4 and info["answer_pages"] == 1 and info["blank_pages"] == 1
    assert len(r.pages) == info["total_pages"] == 6
    assert r.pages[-1].extract_text().strip() == ""


def test_pdf_is_genuinely_vector_and_print_ready(result):
    res, _ = result
    for style in ("rounded_rect", "circle", "line", "highlight"):
        pdf, info = build_pdf(
            [(c.puzzle, c.title) for c in res.succeeded[:2]],
            PageLayout(),
            PdfOptions(per_page_answers=2, answer_style=style),
        )
        vec = inspect_pdf_vectors(pdf)
        assert vec["images"] == 0
        assert vec["vector_ops"] > 100
        assert b"/Subtype /Image" not in pdf and b"/DCTDecode" not in pdf
        assert all(f["emb"] for f in info["pdf_fonts"])


def test_pdf_text_is_selectable_letters(result):
    res, _ = result
    p = res.succeeded[0].puzzle
    pdf, _ = build_pdf([(p, "T")], options=PdfOptions(include_answers=False))
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text().replace("\n", "")
    letters = "".join("".join(r) for r in p.grid)
    assert letters in text.replace(" ", "") or all(ch in text for ch in set(letters))


def test_all_dropdown_fonts_are_embedded():
    puz = generate_puzzle(FRUIT, PuzzleConfig(seed=1))
    fams = available_fonts()
    assert len(fams) >= 8
    for f in fams:
        assert all(f["embedded_styles"].values()), f"Font {f['family']} has unembedded style: {f}"
        layout = PageLayout(
            grid_font=f["family"],
            clue_font=f["family"],
            title_font=f["family"],
        )
        pdf, info = build_pdf([(puz, "Font Test")], layout, PdfOptions(include_answers=False))
        assert b"/FontFile2" in pdf
        pdf_fonts = inspect_pdf_fonts(pdf)
        assert pdf_fonts and all(pf["emb"] for pf in pdf_fonts), pdf_fonts


def test_verify_pdf_aborts_on_invalid_pdf(result):
    res, _ = result
    pdf, info = build_pdf([(c.puzzle, c.title) for c in res.succeeded[:2]])
    with pytest.raises(ValueError, match="page count"):
        verify_pdf(pdf, expected_pages=info["total_pages"] + 2)
    with pytest.raises(ValueError, match="trim size"):
        verify_pdf(pdf, expected_pages=info["total_pages"], expected_width_mm=100, expected_height_mm=100)
    with pytest.raises(ValueError, match="raster image"):
        verify_pdf(pdf + b"\n/Subtype /Image\n")


def test_no_partial_books_when_any_chapter_fails():
    ch = chapters(2) + [("Broken Chapter", ["CAT", "!!!"])]
    res = generate_chapters(ch, PuzzleConfig())
    assert len(res.succeeded) == 2 and len(res.failed) == 1
    with pytest.raises(ValueError, match="Cannot export a partial book"):
        build_book_pdf("My Book", res)


def test_build_book_pdf_refuses_empty():
    res = generate_chapters([("Bad", ["???"])], PuzzleConfig())
    with pytest.raises(ValueError, match="Cannot export a partial book"):
        build_book_pdf("B", res)


def test_pdf_only_export_10_chapters():
    ch = [(f"Chapter {i + 1}: Theme {i + 1}", FRUIT) for i in range(10)]
    t0 = time.perf_counter()
    res = generate_chapters(ch, PuzzleConfig(), base_seed=200)
    layout = PageLayout(
        title_enabled=True,
        title_mode="custom",
        title_text="Puzzle #PUZZLE_NUMBER: CHAPTER_TITLE",
        page_numbers=True,
    )
    opts = PdfOptions(per_page_answers=4, page_numbers=True, title="Ten Chapter Book")
    pdf, info = build_book_pdf("Ten Chapter Book", res, layout, opts)
    elapsed = time.perf_counter() - t0

    assert pdf_filename("Ten Chapter Book") == "ten-chapter-book.pdf"
    plan = page_plan(10, layout.puzzles_per_page, opts.per_page_answers)
    # 10 puzzle pages + 3 solution pages (ceil(10/4)=3) = 13 -> +1 blank = 14 pages
    assert plan == {"chapters": 10, "puzzle_pages": 10, "solution_pages": 3, "blank_pages": 1, "total_pages": 14}
    assert info["total_pages"] == plan["total_pages"] == 14
    assert info["vector_check"]["images"] == 0
    assert info["vector_check"]["vector_ops"] > 500
    assert all(f["emb"] for f in info["pdf_fonts"])

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 14
    outline_titles = [o.title for o in reader.outline]
    assert len(outline_titles) == 10 + 1
    assert outline_titles[0] == "Puzzle #1: Chapter 1: Theme 1"
    assert outline_titles[9] == "Puzzle #10: Chapter 10: Theme 10"
    assert outline_titles[-1] == "Solutions"

    first_text = reader.pages[0].extract_text()
    assert "Puzzle #1: Chapter 1: Theme 1" in first_text and "APPLE" in first_text
    last_sol_text = reader.pages[12].extract_text()
    assert "Answer Key: Puzzle #9" in last_sol_text and "Answer Key: Puzzle #10" in last_sol_text
    assert reader.pages[13].extract_text().strip() == ""
    assert elapsed < 30.0


def test_pdf_only_export_365_chapters():
    words_10 = ["APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON", "PEACH", "CHERRY", "PAPAYA", "GUAVA"]
    ch = [(f"Day {i + 1}", words_10) for i in range(365)]
    t0 = time.perf_counter()
    res = generate_chapters(ch, PuzzleConfig(attempts_per_size=15), base_seed=1000)
    t_gen = time.perf_counter() - t0
    assert len(res.succeeded) == 365 and len(res.failed) == 0

    layout = PageLayout(
        title_enabled=True,
        title_mode="custom",
        title_text="Puzzle #PUZZLE_NUMBER - CHAPTER_TITLE",
        page_numbers=True,
        margin_mode="kdp",
    )
    opts = PdfOptions(per_page_answers=6, page_numbers=True, title="Year of Word Searches")
    t1 = time.perf_counter()
    pdf, info = build_book_pdf("Year of Word Searches", res, layout, opts)
    t_pdf = time.perf_counter() - t1

    plan = page_plan(365, layout.puzzles_per_page, opts.per_page_answers)
    # 365 puzzle pages + ceil(365/6)=61 solution pages = 426 (even -> 0 blank pages)
    assert plan == {"chapters": 365, "puzzle_pages": 365, "solution_pages": 61, "blank_pages": 0, "total_pages": 426}
    assert info["total_pages"] == plan["total_pages"] == 426
    assert info["vector_check"]["images"] == 0
    assert info["vector_check"]["vector_ops"] > 10000
    assert all(f["emb"] for f in info["pdf_fonts"])

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 426
    outline_titles = [o.title for o in reader.outline]
    assert len(outline_titles) == 365 + 1
    assert outline_titles[0] == "Puzzle #1 - Day 1"
    assert outline_titles[364] == "Puzzle #365 - Day 365"
    assert outline_titles[-1] == "Solutions"

    first_page_text = reader.pages[0].extract_text()
    last_puzzle_text = reader.pages[364].extract_text()
    last_page_text = reader.pages[-1].extract_text()
    assert "Puzzle #1 - Day 1" in first_page_text and "APPLE" in first_page_text
    assert "Puzzle #365 - Day 365" in last_puzzle_text and "365" in last_puzzle_text
    assert "Answer Key: Puzzle #361" in last_page_text and "Answer Key: Puzzle #365" in last_page_text and "426" in last_page_text
    assert (t_gen + t_pdf) < 120.0
