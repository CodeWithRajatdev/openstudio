import math
import xml.etree.ElementTree as ET

import pytest

from app.wordsearch.engine import Difficulty, PuzzleConfig, difficulty_preset, generate_puzzle
from app.wordsearch.render import (HIGHLIGHT_STYLES, LayoutError, PageLayout, build_answer_key,
                        fill_placeholders, kdp_gutter_mm, layout_for_page, page_plan,
                        render_answer_key_page, render_answer_key_pages,
                        render_answer_key_svg, render_puzzle_page, render_puzzle_svg,
                        resolve_solution_title, resolve_title, sort_clues)

NS = "{http://www.w3.org/2000/svg}"
WORDS = ["APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON", "PEACH", "CHERRY",
         "PAPAYA", "GUAVA", "KIWI", "PLUM"]


@pytest.fixture(scope="module")
def puzzle():
    return generate_puzzle(WORDS, difficulty_preset(Difficulty.HARD, seed=7), puzzle_id="p1")


def parse(svg):
    return ET.fromstring(svg)   # raises on invalid XML


def assert_pure_vector(svg):
    root = parse(svg)
    tags = {e.tag.replace(NS, "") for e in root.iter()}
    assert "image" not in tags and "foreignObject" not in tags
    assert "data:image" not in svg and "base64" not in svg
    assert "png" not in svg.lower() and "jpg" not in svg.lower()


# ---- answer-key data ------------------------------------------------------
def test_answer_key_entries_match_placements(puzzle):
    entries = build_answer_key(puzzle)
    assert len(entries) == len(WORDS)
    for e, p in zip(entries, puzzle.placements):
        assert e.original == p.original
        assert e.start == (p.start_row + 1, p.start_col + 1)
        assert e.end == (p.end_row + 1, p.end_col + 1)
        assert "".join(puzzle.grid[r][c] for r, c in e.cells) == p.grid_word
        assert e.describe().startswith(p.original)


# ---- puzzle svg ---------------------------------------------------------------
def test_puzzle_svg_is_valid_vector_with_viewbox(puzzle):
    svg = render_puzzle_svg(puzzle, "Chapter 1: Fruits")
    root = parse(svg)
    assert root.attrib["viewBox"] == "0 0 215.9 279.4"
    assert root.attrib["width"] == "215.9mm" and root.attrib["height"] == "279.4mm"
    assert_pure_vector(svg)


def test_puzzle_svg_contains_every_letter_and_clue(puzzle):
    root = parse(render_puzzle_svg(puzzle, "T"))
    letters = [t.text for g in root.iter(NS + "g") if g.attrib.get("class") == "grid-letters"
               for t in g]
    assert len(letters) == puzzle.rows * puzzle.cols
    assert "".join(letters) == "".join("".join(r) for r in puzzle.grid)
    clues = [t.text for g in root.iter(NS + "g") if g.attrib.get("class") == "clue-list"
             for t in g]
    assert sorted(clues) == sorted(w.upper() for w in WORDS)


def test_grid_lines_are_a_vector_path(puzzle):
    root = parse(render_puzzle_svg(puzzle))
    paths = [e for e in root.iter(NS + "path") if e.attrib.get("class") == "grid-lines"]
    assert len(paths) == 1
    d = paths[0].attrib["d"]
    assert d.count("H") == puzzle.rows + 1 and d.count("V") == puzzle.cols + 1


def test_special_characters_are_escaped():
    puz = generate_puzzle(["RD", "AB", "TOMS"], PuzzleConfig(seed=1))
    svg = render_puzzle_svg(puz, "Tom & <Jerry>", clue_words=["R&D", "A<B", "TOM'S"])
    root = parse(svg)
    clues = [t.text for g in root.iter(NS + "g") if g.attrib.get("class") == "clue-list"
             for t in g]
    assert clues == ["R&D", "A<B", "TOM'S"]


@pytest.mark.parametrize("cols", [1, 2, 3, 4])
def test_clue_columns(puzzle, cols):
    svg = render_puzzle_svg(puzzle, "T", PageLayout(clue_columns=cols))
    root = parse(svg)
    xs = {t.attrib["x"] for g in root.iter(NS + "g") if g.attrib.get("class") == "clue-list"
          for t in g}
    assert len(xs) == cols


def test_layout_errors_are_raised_not_hidden(puzzle):
    with pytest.raises(LayoutError):
        render_puzzle_svg(puzzle, "T", PageLayout(page_width=40, page_height=60, margin=5))
    with pytest.raises(LayoutError):
        PageLayout(clue_columns=5).validate()


def test_large_grid_shrinks_cells_to_fit():
    words = [f"WORD{chr(65 + i)}{chr(65 + j)}" for i in range(5) for j in range(5)]
    puz = generate_puzzle(words, PuzzleConfig(seed=2))
    svg = render_puzzle_svg(puz, "Big")
    parse(svg)


# ---- answer-key svg -------------------------------------------------------------
@pytest.mark.parametrize("style", HIGHLIGHT_STYLES)
def test_every_highlight_style_has_one_shape_per_word(puzzle, style):
    svg = render_answer_key_svg(puzzle, "Fruits", style=style)
    assert_pure_vector(svg)
    root = parse(svg)
    hl = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "answer-highlights"][0]
    assert len(list(hl)) == len(puzzle.placements)
    assert {e.attrib["data-word"] for e in hl} == set(WORDS)


def test_line_highlight_endpoints_hit_exact_cell_centres(puzzle):
    layout = PageLayout()
    svg = render_answer_key_svg(puzzle, "T", layout, style="line")
    root = parse(svg)
    grid = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "answer-grid"][0]
    hl = [g for g in grid.iter(NS + "g") if g.attrib.get("class") == "answer-highlights"][0]
    by_word = {p.original: p for p in puzzle.placements}
    # recover cell size from grid line path
    path = [e for e in grid.iter(NS + "path")][0].attrib["d"]
    width = float(path.split("H")[1].split("M")[0])
    cell = width / puzzle.cols
    for line in hl:
        p = by_word[line.attrib["data-word"]]
        assert math.isclose(float(line.attrib["x1"]), (p.start_col + 0.5) * cell, abs_tol=0.01)
        assert math.isclose(float(line.attrib["y1"]), (p.start_row + 0.5) * cell, abs_tol=0.01)
        assert math.isclose(float(line.attrib["x2"]), (p.end_col + 0.5) * cell, abs_tol=0.01)
        assert math.isclose(float(line.attrib["y2"]), (p.end_row + 0.5) * cell, abs_tol=0.01)


def test_answer_key_grid_letters_match_puzzle_grid(puzzle):
    a = parse(render_puzzle_svg(puzzle, "T"))
    b = parse(render_answer_key_svg(puzzle, "T"))
    def letters(root):
        return "".join(t.text for g in root.iter(NS + "g")
                       if g.attrib.get("class") == "grid-letters" for t in g)
    assert letters(a) == letters(b)


@pytest.mark.parametrize("per_page", [1, 2, 4, 6])
def test_answer_key_sheets_hold_n_puzzles(per_page):
    puzzles = [generate_puzzle(WORDS[:8], PuzzleConfig(seed=i), puzzle_id=f"p{i}")
               for i in range(per_page)]
    svg = render_answer_key_page([(p, f"Ch {i + 1}") for i, p in enumerate(puzzles)], per_page)
    assert_pure_vector(svg)
    root = parse(svg)
    grids = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "answer-grid"]
    assert [g.attrib["data-puzzle-id"] for g in grids] == [p.puzzle_id for p in puzzles]


def test_pagination_and_bad_inputs(puzzle):
    items = [(puzzle, f"Ch {i}") for i in range(5)]
    pages = render_answer_key_pages(items, per_page=2)
    assert len(pages) == 3
    with pytest.raises(ValueError):
        render_answer_key_page(items[:3], per_page=2)
    with pytest.raises(ValueError):
        render_answer_key_page(items[:1], per_page=3)
    with pytest.raises(ValueError):
        render_answer_key_svg(puzzle, style="wavy")


# ---- step C customization features ----------------------------------------
def test_title_placeholders_and_disabled(puzzle):
    layout = PageLayout(title_enabled=True, title_mode="custom",
                        title_text="Puzzle #PUZZLE_NUMBER - CHAPTER_TITLE",
                        title_start_number=10)
    assert resolve_title(layout, "Fruits", 2) == "Puzzle #12 - Fruits"
    svg = render_puzzle_svg(puzzle, "Fruits", layout, index=2)
    root = parse(svg)
    titles = [t.text for t in root.iter(NS + "text") if t.attrib.get("class") == "title"]
    assert titles == ["Puzzle #12 - Fruits"]

    no_title = PageLayout(title_enabled=False)
    root_no = parse(render_puzzle_svg(puzzle, "Fruits", no_title, index=2))
    assert [t for t in root_no.iter(NS + "text") if t.attrib.get("class") == "title"] == []


def test_clue_sorting_modes(puzzle):
    assert sort_clues(WORDS, "short_long")[0] in ("KIWI", "PLUM")
    assert len(sort_clues(WORDS, "long_short")[0]) >= len(sort_clues(WORDS, "long_short")[-1])
    assert sort_clues(WORDS, "alpha") == sorted(WORDS)
    assert sort_clues(WORDS, "file") == WORDS
    r1 = sort_clues(WORDS, "random", seed=42)
    r2 = sort_clues(WORDS, "random", seed=42)
    assert r1 == r2 and sorted(r1) == sorted(WORDS)


@pytest.mark.parametrize("clue_type", ["columns", "rows", "inline"])
@pytest.mark.parametrize("clue_align", ["left", "center", "right"])
def test_clue_layout_types_and_alignment(puzzle, clue_type, clue_align):
    layout = PageLayout(clue_type=clue_type, clue_align=clue_align, clue_sort="short_long")
    svg = render_puzzle_svg(puzzle, "Fruits", layout)
    root = parse(svg)
    clues = [t.text for g in root.iter(NS + "g") if g.attrib.get("class") == "clue-list"
             for t in g]
    assert sorted(clues) == sorted(w.upper() for w in WORDS)


def test_additional_margins_and_puzzle_alignment(puzzle):
    left_layout = PageLayout(extra_margins=True, margin=15, margin_left=10,
                             puzzle_align="left")
    right_layout = PageLayout(extra_margins=True, margin=15, margin_left=10,
                              puzzle_align="right")
    root_l = parse(render_puzzle_svg(puzzle, "T", left_layout))
    root_r = parse(render_puzzle_svg(puzzle, "T", right_layout))
    gl = [g for g in root_l.iter(NS + "g") if g.attrib.get("class") == "grid"][0]
    gr = [g for g in root_r.iter(NS + "g") if g.attrib.get("class") == "grid"][0]
    xl = float(gl.attrib["transform"].split("(")[1].split()[0])
    xr = float(gr.attrib["transform"].split("(")[1].split()[0])
    assert math.isclose(xl, 25.0, abs_tol=0.01)
    assert xr > xl


def test_cell_fill_outer_border_and_solution_overrides(puzzle):
    layout = PageLayout(
        cell_color="#ffeeaa", border_width=0.6, border_color="#123456",
        solution_font="Georgia", solution_letter_color="#0055aa",
        solution_line_color="#990000", highlight_color="#00aa55",
        solution_title_text="Solution #PUZZLE_NUMBER", title_start_number=5,
    )
    p_root = parse(render_puzzle_svg(puzzle, "Fruits", layout, index=1))
    assert any(r.attrib.get("class") == "cell-fill" and r.attrib.get("fill") == "#ffeeaa"
               for r in p_root.iter(NS + "rect"))
    assert any(r.attrib.get("class") == "grid-border" and r.attrib.get("stroke") == "#123456"
               for r in p_root.iter(NS + "rect"))

    a_root = parse(render_answer_key_svg(puzzle, "Fruits", layout, style="line", index=1))
    key_titles = [t.text for t in a_root.iter(NS + "text") if t.attrib.get("class") == "key-title"]
    assert key_titles == ["Solution #6"]
    letters_g = [g for g in a_root.iter(NS + "g") if g.attrib.get("class") == "grid-letters"][0]
    assert letters_g.attrib["fill"] == "#0055aa"
    assert "Georgia" in letters_g.attrib["font-family"]
    hl = [g for g in a_root.iter(NS + "g") if g.attrib.get("class") == "answer-highlights"][0]
    assert all(el.attrib["stroke"] == "#00aa55" for el in hl)


@pytest.mark.parametrize("per_page", [1, 2, 4])
def test_multi_puzzle_page(puzzle, per_page):
    layout = PageLayout(puzzles_per_page=per_page, title_mode="custom",
                        title_text="Puzzle #PUZZLE_NUMBER", title_start_number=1)
    items = [(puzzle, f"Ch {i + 1}", i) for i in range(per_page)]
    svg = render_puzzle_page(items, layout, page_number=3)
    root = parse(svg)
    blocks = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "puzzle"]
    assert len(blocks) == per_page
    titles = [t.text for t in root.iter(NS + "text") if t.attrib.get("class") == "title"]
    assert titles == [f"Puzzle #{i + 1}" for i in range(per_page)]


def test_kdp_margin_mode_mirrors_gutter_and_page_plan():
    plan = page_plan(chapters=100, puzzles_per_page=1, solutions_per_page=6)
    assert plan == {"chapters": 100, "puzzle_pages": 100, "solution_pages": 17,
                    "blank_pages": 1, "total_pages": 118}
    assert kdp_gutter_mm(118) == 9.53
    assert kdp_gutter_mm(200) == 12.7
    layout = PageLayout(margin=6.0, margin_mode="kdp")
    p1 = layout_for_page(layout, page_number=1, total_pages=200)
    p2 = layout_for_page(layout, page_number=2, total_pages=200)
    assert p1.ml == 12.7 and p1.mr == 6.35
    assert p2.ml == 6.35 and p2.mr == 12.7


def test_title_and_clue_gaps(puzzle):
    def _positions(title_gap, clue_gap):
        root = parse(render_puzzle_svg(puzzle, "Title", PageLayout(title_gap=title_gap, clue_gap=clue_gap)))
        grid_g = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "grid"][0]
        gy = float(grid_g.attrib["transform"].split()[1].rstrip(")"))
        clue_g = [g for g in root.iter(NS + "g") if g.attrib.get("class") == "clue-list"][0]
        cy = min(float(t.attrib["y"]) for t in clue_g.iter(NS + "text"))
        return gy, cy

    gy0, cy0 = _positions(0.0, 2.0)
    gy1, cy1 = _positions(10.0, 2.0)
    assert gy1 - gy0 == pytest.approx(10.0, abs=0.05)
    assert cy1 - cy0 == pytest.approx(10.0, abs=0.05)

    gy2, cy2 = _positions(10.0, 14.0)
    assert gy2 == pytest.approx(gy1, abs=0.05)
    assert cy2 - cy1 == pytest.approx(12.0, abs=0.05)

    with pytest.raises(LayoutError):
        PageLayout(title_gap=-1.0).validate()
    with pytest.raises(LayoutError):
        PageLayout(clue_gap=-0.5).validate()



