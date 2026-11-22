"""Book assembly, unified page plan calculator, bookmarks, and verified single PDF export."""
from __future__ import annotations

from typing import Any

from .geometry import (
     VALID_SOLUTIONS_PER_PAGE,
    ExportPuzzleData,
    _new_page,
    build_export_pages,
    build_solution_pages,
    page_content_x_and_w,
)
from .primitives import PagePrimitives, TextPrimitive
from .renderers import render_pdf
from .settings import ExportSettings, resolve_page_dimensions
from .verifier import verify_pdf


def assemble_book_pages_and_plan(
    chapter_puzzles: list[tuple[int, str, ExportPuzzleData]],
    settings: ExportSettings,
    *,
    solutions_per_page: int = 4,
    start_puzzles_on_right_hand_page: bool = False,
    show_page_numbers: bool = True,
    clue_placement: str = "same_page",
    font_dir: str = "",
) -> tuple[list[PagePrimitives], dict[str, Any]]:
    """Single source of truth for book pagination and PDF page assembly."""
    width_pt, height_pt = resolve_page_dimensions(settings)
    pages: list[PagePrimitives] = []

    front_matter_blank_pages = 0
    if start_puzzles_on_right_hand_page:
        blank_front = _new_page(width_pt, height_pt, settings)
        blank_front.is_blank = True
        pages.append(blank_front)
        front_matter_blank_pages = 1

    chapter_breakdown: list[dict[str, Any]] = []
    puzzle_pages_total = 0

    for idx, (chapter_id, chapter_name, exp_puzzle) in enumerate(chapter_puzzles, start=1):
        start_page = len(pages) + 1
        if clue_placement == "facing_page":
            ch_pages = build_export_pages(
                exp_puzzle,
                "puzzle",
                settings,
                font_dir=font_dir,
                start_page_number=start_page,
            )
            ch_pages.extend(
                build_export_pages(
                    exp_puzzle,
                    "clues",
                    settings,
                    font_dir=font_dir,
                    start_page_number=start_page + len(ch_pages),
                )
            )
        else:
            ch_pages = build_export_pages(
                exp_puzzle,
                "puzzle_with_clues",
                settings,
                font_dir=font_dir,
                start_page_number=start_page,
            )

        if ch_pages:
            ch_pages[0].bookmark = exp_puzzle.title or chapter_name
        pages.extend(ch_pages)
        puzzle_pages_total += len(ch_pages)

        chapter_breakdown.append(
            {
                "chapter_id": chapter_id,
                "chapter_number": idx,
                "chapter_name": chapter_name,
                "title": exp_puzzle.title or chapter_name,
                "start_page": start_page,
                "puzzle_pages": len(ch_pages),
                "word_count": len(exp_puzzle.entries),
            }
        )

    solutions_start_page = len(pages) + 1 if chapter_puzzles else None
    sol_pages = build_solution_pages(
        [p for _, _, p in chapter_puzzles],
        settings,
        solutions_per_page=solutions_per_page,
        start_page_number=solutions_start_page or 1,
    )
    pages.extend(sol_pages)
    solution_pages_total = len(sol_pages)

    trailing_blank_pages = 0
    if len(pages) > 0 and len(pages) % 2 == 1:
        blank_end = _new_page(width_pt, height_pt, settings)
        blank_end.is_blank = True
        pages.append(blank_end)
        trailing_blank_pages = 1

    if show_page_numbers and pages:
        footer_size = max(8.0, min(10.0, settings.clue_font_size))
        footer_y = max(height_pt - max(12.0, settings.margin_bottom * 0.45), height_pt - 24.0)
        for p_num, page in enumerate(pages, start=1):
            if page.is_blank:
                continue
            p_cx, p_cw = page_content_x_and_w(width_pt, settings, page_number=p_num)
            center_x = p_cx + p_cw / 2.0
            page.primitives.append(
                TextPrimitive(
                    x=center_x,
                    y=footer_y,
                    text=str(p_num),
                    font_size=footer_size,
                    font_family=settings.font_family,
                    bold=False,
                    color=settings.ink_color,
                    anchor="middle",
                )
            )

    odd_cx, content_w = page_content_x_and_w(width_pt, settings, page_number=1)
    even_cx, _ = page_content_x_and_w(width_pt, settings, page_number=2)
    page_plan = {
        "front_matter_blank_pages": front_matter_blank_pages,
        "puzzle_pages": puzzle_pages_total,
        "solution_pages": solution_pages_total,
        "solutions_per_page": solutions_per_page if solutions_per_page in VALID_SOLUTIONS_PER_PAGE else 4,
        "trailing_blank_pages": trailing_blank_pages,
        "blank_pages": front_matter_blank_pages + trailing_blank_pages,
        "total_pages": len(pages),
        "start_puzzles_on_right_hand_page": bool(start_puzzles_on_right_hand_page),
        "solutions_start_page": solutions_start_page,
        "width_pt": width_pt,
        "height_pt": height_pt,
        "odd_page_content_x_pt": odd_cx,
        "even_page_content_x_pt": even_cx,
        "content_width_pt": content_w,
        "chapters": chapter_breakdown,
    }
    return pages, page_plan


def compute_book_page_plan(
    chapter_puzzles: list[tuple[int, str, ExportPuzzleData]],
    settings: ExportSettings,
    *,
    solutions_per_page: int = 4,
    start_puzzles_on_right_hand_page: bool = False,
    show_page_numbers: bool = True,
    clue_placement: str = "same_page",
    font_dir: str = "",
) -> dict[str, Any]:
    """Return the exact page plan computed from the actual export geometry."""
    _, plan = assemble_book_pages_and_plan(
        chapter_puzzles,
        settings,
        solutions_per_page=solutions_per_page,
        start_puzzles_on_right_hand_page=start_puzzles_on_right_hand_page,
        show_page_numbers=show_page_numbers,
        clue_placement=clue_placement,
        font_dir=font_dir,
    )
    return plan


def build_book_pdf(
    chapter_puzzles: list[tuple[int, str, ExportPuzzleData]],
    settings: ExportSettings,
    *,
    solutions_per_page: int = 4,
    start_puzzles_on_right_hand_page: bool = False,
    show_page_numbers: bool = True,
    clue_placement: str = "same_page",
    font_dir: str = "",
    verify: bool = True,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    """Assemble and render a complete book PDF, automatically running verify_pdf."""
    if not chapter_puzzles:
        raise ValueError("Cannot build a book PDF with 0 chapters.")

    pages, plan = assemble_book_pages_and_plan(
        chapter_puzzles,
        settings,
        solutions_per_page=solutions_per_page,
        start_puzzles_on_right_hand_page=start_puzzles_on_right_hand_page,
        show_page_numbers=show_page_numbers,
        clue_placement=clue_placement,
        font_dir=font_dir,
    )
    pdf_bytes = render_pdf(pages, font_dir=font_dir)

    verification: dict[str, Any]
    if verify:
        verification = verify_pdf(
            pdf_bytes,
            expected_page_count=plan["total_pages"],
            expected_width_pt=plan["width_pt"],
            expected_height_pt=plan["height_pt"],
            raise_on_failure=True,
        )
    else:
        verification = {"valid": True, "checks": {}, "errors": []}

    return pdf_bytes, plan, verification
