"""Checkpoint 4 tests: unified geometry, SVG/PDF/PNG renderers, page presets, multi-page flow."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from app.crossword.services.export.renderers import render_pdf, render_png, render_svg
from app.crossword.services.export.settings import ExportSettings, resolve_page_dimensions


def _sample_puzzle() -> ExportPuzzleData:
    return ExportPuzzleData(
        title="Sample Puzzle",
        rows=5,
        cols=5,
        grid=[
            "APPLE",
            "L###A",
            "P###R",
            "H###T",
            "A###H",
        ],
        entries=[
            ExportEntry(number=1, direction="A", row=0, col=0, answer="APPLE", clue="Crisp orchard fruit."),
            ExportEntry(number=1, direction="D", row=0, col=0, answer="ALPHA", clue="First Greek letter."),
            ExportEntry(number=2, direction="D", row=0, col=4, answer="EARTH", clue="Third planet from the Sun."),
        ],
    )


def test_page_size_presets_and_custom_units():
    assert resolve_page_dimensions(ExportSettings(page_size="letter")) == (612.0, 792.0)
    assert resolve_page_dimensions(ExportSettings(page_size="6x9")) == (432.0, 648.0)
    assert resolve_page_dimensions(ExportSettings(page_size="8x10")) == (576.0, 720.0)
    assert resolve_page_dimensions(ExportSettings(page_size="8.5x8.5")) == (612.0, 612.0)
    w_a4, h_a4 = resolve_page_dimensions(ExportSettings(page_size="a4"))
    assert 595.0 < w_a4 < 596.0 and 841.0 < h_a4 < 842.0

    assert resolve_page_dimensions(
        ExportSettings(page_size="custom", custom_width=100, custom_height=200, custom_unit="pt")
    ) == (100.0, 200.0)
    w_cm, _ = resolve_page_dimensions(
        ExportSettings(page_size="custom", custom_width=2.54, custom_height=2.54, custom_unit="cm")
    )
    assert w_cm == pytest.approx(72.0, abs=0.01)


def test_svg_is_pure_vector_and_hides_answers_in_puzzle():
    puzzle = _sample_puzzle()
    settings = ExportSettings(page_size="letter", show_clue_lengths=True)

    blank_pages = build_export_pages(puzzle, "puzzle", settings)
    blank_svg = render_svg(blank_pages[0])
    root = ET.fromstring(blank_svg)
    tags = {el.tag.split("}")[-1] for el in root.iter()}
    assert "image" not in tags
    assert {"svg", "rect", "line", "text"}.issubset(tags)
    blank_texts = [el.text for el in root.iter() if el.tag.endswith("text")]
    assert "Sample Puzzle" in blank_texts
    assert "1" in blank_texts
    assert "2" in blank_texts
    assert "P" not in blank_texts  # answer letters hidden

    key_pages = build_export_pages(puzzle, "answer_key", settings)
    key_svg = render_svg(key_pages[0])
    key_root = ET.fromstring(key_svg)
    key_tags = {el.tag.split("}")[-1] for el in key_root.iter()}
    assert "image" not in key_tags
    key_texts = [el.text for el in key_root.iter() if el.tag.endswith("text")]
    assert "P" in key_texts
    assert "E" in key_texts


def test_multipage_clues_pdf_and_png():
    many_entries = [
        ExportEntry(
            number=i,
            direction="A" if i % 2 else "D",
            row=0,
            col=0,
            answer="PLANET",
            clue=f"Clue number {i} with enough words to wrap across lines cleanly.",
        )
        for i in range(1, 65)
    ]
    puzzle = ExportPuzzleData(
        title="Big Clue List",
        rows=5,
        cols=5,
        grid=["APPLE", "L###A", "P###R", "H###T", "A###H"],
        entries=many_entries,
    )
    settings = ExportSettings(page_size="6x9", dpi=150)

    clue_pages = build_export_pages(puzzle, "clues", settings)
    assert len(clue_pages) >= 2

    pdf_bytes = render_pdf(clue_pages)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000

    combo_pages = build_export_pages(puzzle, "puzzle_with_clues", settings)
    assert len(combo_pages) >= 2

    png_bytes = render_png(combo_pages[0], dpi=150)
    img = Image.open(io.BytesIO(png_bytes))
    assert img.format == "PNG"
    # 6x9 inches at 150 DPI = 900 x 1350 px
    assert img.size == (900, 1350)


def test_export_render_endpoint():
    with TestClient(app) as client:
        payload = {
            "title": "API Export",
            "rows": 3,
            "cols": 3,
            "grid": ["CAT", "A#O", "R#P"],
            "entries": [
                {"number": 1, "direction": "A", "row": 0, "col": 0, "answer": "CAT", "clue": "Feline."},
                {"number": 1, "direction": "D", "row": 0, "col": 0, "answer": "CAR", "clue": "Vehicle."},
                {"number": 2, "direction": "D", "row": 0, "col": 2, "answer": "TOP", "clue": "Spinning toy."},
            ],
            "kind": "puzzle_with_clues",
            "format": "svg",
        }
        svg_res = client.post("/api/export/render", json=payload)
        assert svg_res.status_code == 200
        assert svg_res.headers["content-type"].startswith("image/svg+xml")
        assert "<image" not in svg_res.text

        payload["format"] = "pdf"
        pdf_res = client.post("/api/export/render", json=payload)
        assert pdf_res.status_code == 200
        assert pdf_res.content.startswith(b"%PDF-")

        payload["format"] = "png"
        payload["settings"] = {"dpi": 100}
        png_res = client.post("/api/export/render", json=payload)
        assert png_res.status_code == 200
        assert png_res.content.startswith(b"\x89PNG")


def test_fonts_css_and_file_endpoints_and_per_element_fonts():
    with TestClient(app) as client:
        css_res = client.get("/api/export/fonts.css")
        assert css_res.status_code == 200
        assert "text/css" in css_res.headers["content-type"]
        assert "@font-face" in css_res.text
        assert "Open Sans" in css_res.text
        assert "Vera" in css_res.text

        ttf_res = client.get("/api/export/fonts/file", params={"family": "Open Sans"})
        assert ttf_res.status_code == 200
        assert len(ttf_res.content) > 1000

        payload = {
            "title": "Styled Puzzle",
            "rows": 3,
            "cols": 3,
            "grid": ["CAT", "A#O", "R#P"],
            "entries": [
                {"number": 1, "direction": "A", "row": 0, "col": 0, "answer": "CAT", "clue": "Feline."},
                {"number": 1, "direction": "D", "row": 0, "col": 0, "answer": "CAR", "clue": "Vehicle."},
                {"number": 2, "direction": "D", "row": 0, "col": 2, "answer": "TOP", "clue": "Spinning toy."},
            ],
            "kind": "puzzle_with_clues",
            "format": "svg",
            "settings": {
                "font_family": "Open Sans",
                "title_font_family": "Vera",
                "title_color": "#112233",
                "title_alignment": "center",
                "clue_font_family": "Vera",
                "clue_color": "#223344",
                "number_font_family": "Vera",
                "number_color": "#334455",
            },
        }
        svg_res = client.post("/api/export/render", json=payload)
        assert svg_res.status_code == 200
        svg_text = svg_res.text
        assert 'font-family="Vera"' in svg_text
        assert 'fill="#112233"' in svg_text
        assert 'text-anchor="middle"' in svg_text
        assert 'fill="#223344"' in svg_text
        assert 'fill="#334455"' in svg_text
