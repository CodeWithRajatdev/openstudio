"""The whole book: page plan, per-page margins and page rendering.

One function (`render_book_page`) draws every page. The live preview, the
exported SVG files and the PDF all call it, so the three always match.

Page order: puzzle pages, then solution pages, then one blank page when the
total would be odd (printed books have two sides per sheet).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from .layout import PageLayout
from .svg import _svg_open, render_answer_key_page, render_puzzle_page

# Amazon KDP paperback (no bleed) minimum margins.
# Inside (gutter) margin grows with the page count; outside/top/bottom >= 0.25 in.
KDP_GUTTER_MM = ((150, 9.53), (300, 12.7), (500, 15.88), (700, 19.05))
KDP_GUTTER_MAX_MM = 22.23
KDP_OUTSIDE_MM = 6.35


def page_plan(chapters: int, puzzles_per_page: int = 1, solutions_per_page: int = 1,
              include_solutions: bool = True) -> dict:
    """puzzle pages = chapters / puzzles per page, solution pages = chapters /
    solutions per page (both rounded up), +1 blank page when the total is odd."""
    ch = max(0, int(chapters))
    ppp = max(1, int(puzzles_per_page))
    spp = max(1, int(solutions_per_page))
    puzzle_pages = math.ceil(ch / ppp)
    solution_pages = math.ceil(ch / spp) if include_solutions else 0
    blank = (puzzle_pages + solution_pages) % 2
    return {"chapters": ch, "puzzle_pages": puzzle_pages, "solution_pages": solution_pages,
            "blank_pages": blank, "total_pages": puzzle_pages + solution_pages + blank}


def kdp_gutter_mm(total_pages: int) -> float:
    for limit, mm_val in KDP_GUTTER_MM:
        if total_pages <= limit:
            return mm_val
    return KDP_GUTTER_MAX_MM


def kdp_margins(margin: float, total_pages: int) -> dict:
    """Effective KDP margins in mm: the KDP minimum, or `margin` when larger."""
    return {"inside": max(margin, kdp_gutter_mm(total_pages)),
            "outside": max(margin, KDP_OUTSIDE_MM)}


def layout_for_page(layout: PageLayout, page_number: int, total_pages: int) -> PageLayout:
    """Layout with the real margins of book page `page_number` (1-based).

    In KDP mode odd pages are right-hand pages (binding on the left), even pages
    are left-hand pages (binding on the right)."""
    if layout.margin_mode != "kdp":
        return layout
    m = kdp_margins(layout.margin, total_pages)
    right_hand = page_number % 2 == 1
    left, right = (m["inside"], m["outside"]) if right_hand else (m["outside"], m["inside"])
    return layout.with_(margin=0.0, extra_margins=True, margin_top=m["outside"],
                        margin_bottom=m["outside"], margin_left=left, margin_right=right)


@dataclass
class BookPage:
    kind: str                    # "puzzle" | "solution" | "blank"
    number: int                  # 1-based page number in the book
    positions: list[int]         # positions (0-based) of the chapters on this page
    section_index: int           # 0-based page index inside its section


def book_pages(n_chapters: int, puzzles_per_page: int, solutions_per_page: int,
               include_solutions: bool = True) -> list[BookPage]:
    plan = page_plan(n_chapters, puzzles_per_page, solutions_per_page, include_solutions)
    pages: list[BookPage] = []
    num = 0
    for k, start in enumerate(range(0, n_chapters, puzzles_per_page)):
        num += 1
        pages.append(BookPage("puzzle", num, list(range(start, min(n_chapters, start + puzzles_per_page))), k))
    if include_solutions:
        for k, start in enumerate(range(0, n_chapters, solutions_per_page)):
            num += 1
            pages.append(BookPage("solution", num,
                                  list(range(start, min(n_chapters, start + solutions_per_page))), k))
    if plan["blank_pages"]:
        pages.append(BookPage("blank", num + 1, [], 0))
    return pages


def section_page_number(kind: str, section_index: int, n_chapters: int,
                        puzzles_per_page: int) -> int:
    """Book page number of the `section_index`-th puzzle or solution page."""
    if kind == "puzzle":
        return section_index + 1
    return math.ceil(n_chapters / puzzles_per_page) + section_index + 1


def render_book_page(kind: str, items: Sequence[tuple], layout: PageLayout, page_number: int,
                     total_pages: int, solutions_per_page: int = 1,
                     answer_style: str = "rounded_rect") -> str:
    """SVG of one book page.

    items: (puzzle, chapter_title, chapter_position) for the chapters on this page."""
    page_layout = layout_for_page(layout, page_number, total_pages)
    if kind == "puzzle":
        return render_puzzle_page(list(items), page_layout, page_number=page_number)
    if kind == "solution":
        return render_answer_key_page(list(items), solutions_per_page, page_layout, answer_style,
                                      page_number=page_number)
    if kind == "blank":
        return _svg_open(page_layout, "Blank page", "Intentionally blank page") + "</svg>"
    raise ValueError(f"unknown page kind {kind!r}")


def layout_fonts(layout: PageLayout, include_solutions: bool = True,
                 solutions_per_page: int = 1) -> list[tuple[str, str, str]]:
    """Every (font, weight, style) the pages of this book can use."""
    pg, ts, cs = layout.puzzle_grid(), layout.title_style_(), layout.clue_style_()
    uses = [(pg.font, pg.weight, pg.style), (cs.font, cs.weight, cs.style)]
    if layout.title_enabled:
        uses.append((ts.font, ts.weight, ts.style))
    if layout.page_numbers or layout.footer_text:
        uses.append((layout.clue_font, "normal", "normal"))
    if include_solutions:
        sg = layout.solution_grid()
        uses.append((sg.font, sg.weight, sg.style))
        if layout.solution_title_enabled:
            sts = layout.solution_title_style_(solutions_per_page)
            uses.append((sts.font, sts.weight, sts.style))
    return uses


def render_book(items: Sequence[tuple], layout: PageLayout, solutions_per_page: int,
                answer_style: str = "rounded_rect", include_solutions: bool = True,
                ) -> list[tuple[BookPage, Optional[str]]]:
    """Every page of the book in order: [(BookPage, svg)]. Blank pages have svg too."""
    items = list(items)
    pages = book_pages(len(items), layout.puzzles_per_page, solutions_per_page,
                       include_solutions)
    total = len(pages)
    out = []
    for p in pages:
        chunk = [items[i] for i in p.positions]
        out.append((p, render_book_page(p.kind, chunk, layout, p.number, total,
                                        solutions_per_page, answer_style)))
    return out
