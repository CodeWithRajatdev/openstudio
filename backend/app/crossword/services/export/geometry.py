"""Unified geometry builder producing PagePrimitives in points."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...engine.preprocess import format_enumeration
from ..clues.validator import format_clue_for_render
from .fonts import measure_text_width
from .primitives import LinePrimitive, PagePrimitives, RectPrimitive, TextPrimitive
from .settings import ExportSettings, resolve_page_dimensions


@dataclass(frozen=True)
class ExportEntry:
    number: int
    direction: str  # "A" or "D"
    row: int
    col: int
    answer: str
    clue: str
    display: Optional[str] = None


@dataclass(frozen=True)
class ExportPuzzleData:
    title: str
    rows: int
    cols: int
    grid: list[str]
    entries: list[ExportEntry]
    solution_title: Optional[str] = None


def _wrap_text(
    text: str,
    max_width_pt: float,
    font_size: float,
    family: str,
    bold: bool = False,
    font_dir: str = "",
) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for w in words[1:]:
        candidate = f"{current} {w}"
        if measure_text_width(candidate, font_size, family=family, bold=bold, font_dir=font_dir) <= max_width_pt:
            current = candidate
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def _new_page(width_pt: float, height_pt: float, settings: ExportSettings) -> PagePrimitives:
    page = PagePrimitives(width_pt=width_pt, height_pt=height_pt)
    page.primitives.append(
        RectPrimitive(x=0.0, y=0.0, width=width_pt, height=height_pt, fill=settings.bg_color)
    )
    return page


def page_content_x_and_w(
    width_pt: float,
    settings: ExportSettings,
    page_number: int = 1,
) -> tuple[float, float]:
    """Return (content_x, content_w) with binding gutter alternating on the inside spine edge."""
    is_odd = (int(page_number) % 2) == 1
    content_x = settings.margin_left + (settings.gutter if is_odd else 0.0)
    content_w = max(
        72.0,
        width_pt - settings.margin_left - settings.margin_right - settings.gutter,
    )
    return content_x, content_w


def _draw_grid(
    page: PagePrimitives,
    puzzle: ExportPuzzleData,
    *,
    content_x: float,
    content_y: float,
    content_w: float,
    max_grid_h: float,
    show_answers: bool,
    settings: ExportSettings,
) -> float:
    """Draw the crossword grid and return the y coordinate just below it."""
    if puzzle.rows <= 0 or puzzle.cols <= 0:
        return content_y

    cell_size = min(content_w / puzzle.cols, max_grid_h / puzzle.rows)
    grid_w = cell_size * puzzle.cols
    grid_h = cell_size * puzzle.rows

    if settings.grid_alignment == "left":
        gx = content_x
    elif settings.grid_alignment == "right":
        gx = content_x + (content_w - grid_w)
    else:
        gx = content_x + (content_w - grid_w) / 2.0
    gy = content_y

    # Map (row, col) -> smallest entry number at that cell
    cell_numbers: dict[tuple[int, int], int] = {}
    for e in puzzle.entries:
        pos = (e.row, e.col)
        if pos not in cell_numbers or e.number < cell_numbers[pos]:
            cell_numbers[pos] = e.number

    num_font_size = min(
        settings.number_font_size,
        max(2.5 if cell_size < 12.0 else 4.0, cell_size * 0.28),
    )
    let_font_size = min(
        settings.letter_font_size,
        max(4.0 if cell_size < 12.0 else 6.0, cell_size * 0.56),
    )

    num_font_family = settings.number_font_family or settings.font_family
    num_color = settings.number_color or settings.ink_color
    num_pos = settings.number_position or "top_left"
    sol_font_family = settings.solution_font_family or settings.font_family
    sol_color = settings.solution_color or settings.ink_color
    sol_highlight = settings.solution_highlight_style or "bold"

    for r in range(puzzle.rows):
        row_str = puzzle.grid[r] if r < len(puzzle.grid) else ""
        for c in range(puzzle.cols):
            ch = row_str[c] if c < len(row_str) else "#"
            cx = gx + c * cell_size
            cy = gy + r * cell_size

            if ch == "#":
                if settings.black_empty_cells:
                    page.primitives.append(
                        RectPrimitive(
                            x=cx,
                            y=cy,
                            width=cell_size,
                            height=cell_size,
                            fill=settings.block_color,
                            stroke=settings.ink_color,
                            stroke_width=settings.grid_line_width,
                        )
                    )
                continue

            cell_fill = (
                "#E2E8F0"
                if (show_answers and sol_highlight == "shaded" and settings.cell_bg_color.upper() == "#FFFFFF")
                else settings.cell_bg_color
            )
            cell_stroke_w = (
                max(settings.grid_line_width, 1.25)
                if (show_answers and sol_highlight == "outline")
                else settings.grid_line_width
            )

            page.primitives.append(
                RectPrimitive(
                    x=cx,
                    y=cy,
                    width=cell_size,
                    height=cell_size,
                    fill=cell_fill,
                    stroke=settings.ink_color,
                    stroke_width=cell_stroke_w,
                )
            )

            num = cell_numbers.get((r, c))
            if num is not None:
                if num_pos == "top_right":
                    nx = cx + cell_size * 0.92
                    ny = cy + num_font_size * 1.02
                    n_anchor = "end"
                elif num_pos == "bottom_left":
                    nx = cx + cell_size * 0.08
                    ny = cy + cell_size - cell_size * 0.08
                    n_anchor = "start"
                else:
                    nx = cx + cell_size * 0.08
                    ny = cy + num_font_size * 1.02
                    n_anchor = "start"
                page.primitives.append(
                    TextPrimitive(
                        x=nx,
                        y=ny,
                        text=str(num),
                        font_size=num_font_size,
                        font_family=num_font_family,
                        bold=False,
                        color=num_color,
                        anchor=n_anchor,
                    )
                )

            if show_answers:
                letter_text = ch.upper() if settings.capital_letters else ch.lower()
                page.primitives.append(
                    TextPrimitive(
                        x=cx + cell_size * 0.5,
                        y=cy + cell_size * 0.5 + let_font_size * 0.36,
                        text=letter_text,
                        font_size=let_font_size,
                        font_family=sol_font_family,
                        bold=(sol_highlight == "bold"),
                        color=sol_color,
                        anchor="middle",
                    )
                )

    if settings.black_empty_cells and settings.border_line_width > 0:
        # Crisp outer border using 4 lines
        bw = settings.border_line_width
        page.primitives.extend(
            [
                LinePrimitive(gx, gy, gx + grid_w, gy, stroke=settings.ink_color, stroke_width=bw),
                LinePrimitive(gx + grid_w, gy, gx + grid_w, gy + grid_h, stroke=settings.ink_color, stroke_width=bw),
                LinePrimitive(gx + grid_w, gy + grid_h, gx, gy + grid_h, stroke=settings.ink_color, stroke_width=bw),
                LinePrimitive(gx, gy + grid_h, gx, gy, stroke=settings.ink_color, stroke_width=bw),
            ]
        )

    return gy + grid_h


def _draw_clues_flowing(
    pages: list[PagePrimitives],
    puzzle: ExportPuzzleData,
    *,
    width_pt: float,
    height_pt: float,
    content_x: float,
    start_y: float,
    content_w: float,
    top_y: float,
    bottom_y: float,
    settings: ExportSettings,
    font_dir: str,
    start_page_number: int = 1,
) -> None:
    """Flow Across and Down clues across columns/rows/inline and multiple pages as needed."""
    clue_font_family = settings.clue_font_family or settings.font_family
    clue_color = settings.clue_color or settings.ink_color
    clue_spacing = max(0.0, float(settings.clue_spacing))
    layout_mode = settings.clue_layout_mode or "columns"
    heading_style = settings.clue_heading_style or "uppercase"
    sort_mode = settings.clue_sort or "number"

    def _sort_entries(entries_iter):
        if sort_mode == "alphabetical":
            return sorted(entries_iter, key=lambda e: ((e.clue or "").lower(), e.number))
        return sorted(entries_iter, key=lambda e: e.number)

    across = _sort_entries(e for e in puzzle.entries if e.direction == "A")
    down = _sort_entries(e for e in puzzle.entries if e.direction == "D")

    num_cols = 2 if layout_mode in ("columns", "side_by_side") else 1
    col_gap = 18.0 if num_cols == 2 else 0.0
    col_w = (content_w - col_gap) / num_cols
    line_h = settings.clue_font_size * 1.32
    heading_scale = 1.15 if heading_style == "bold" else 1.05
    header_h = settings.clue_font_size * (1.7 if heading_style == "bold" else 1.6)

    def _format_heading(raw: str) -> str:
        if heading_style == "title":
            return raw.title()
        return raw.upper()

    def _format_entry_line(e: ExportEntry) -> str:
        if not settings.show_clue_lengths or settings.enumeration_display in ("none", "off", "false", False):
            suffix = ""
        else:
            enum_str = format_enumeration(e.answer, e.display, style=settings.enumeration_display)
            suffix = f" {enum_str}" if enum_str else ""
        if e.clue:
            clue_text = format_clue_for_render(
                e.clue,
                capitalization=settings.clue_capitalization,
                ending_punctuation=settings.clue_ending_punctuation,
            )
        else:
            clue_text = "[Missing clue]"
        return f"{e.number}. {clue_text}{suffix}"

    if layout_mode == "side_by_side":
        base_page_idx = len(pages) - 1

        def _render_side_column(raw_heading: str, group: list[ExportEntry], col_index: int) -> None:
            if not group:
                return
            col_blocks: list[tuple[str, list[str]]] = [("header", [_format_heading(raw_heading)])]
            for e in group:
                wrapped = _wrap_text(
                    _format_entry_line(e),
                    max_width_pt=col_w,
                    font_size=settings.clue_font_size,
                    family=clue_font_family,
                    font_dir=font_dir,
                )
                col_blocks.append(("item", wrapped))

            p_idx = base_page_idx
            cur_y_col = start_y
            for b_kind, b_lines in col_blocks:
                needed_h = header_h if b_kind == "header" else len(b_lines) * line_h + clue_spacing
                if cur_y_col + needed_h > bottom_y:
                    p_idx += 1
                    while p_idx >= len(pages):
                        pages.append(_new_page(width_pt, height_pt, settings))
                    cur_y_col = top_y

                target_page = pages[p_idx]
                p_origin_x = (
                    content_x
                    if p_idx == base_page_idx
                    else page_content_x_and_w(
                        width_pt,
                        settings,
                        page_number=start_page_number + p_idx,
                    )[0]
                )
                cx_col = p_origin_x + (col_w + col_gap if col_index == 1 else 0.0)

                if b_kind == "header":
                    target_page.primitives.append(
                        TextPrimitive(
                            x=cx_col,
                            y=cur_y_col + settings.clue_font_size * heading_scale,
                            text=b_lines[0],
                            font_size=settings.clue_font_size * heading_scale,
                            font_family=clue_font_family,
                            bold=True,
                            color=clue_color,
                            anchor="start",
                        )
                    )
                    cur_y_col += header_h
                else:
                    for ln in b_lines:
                        target_page.primitives.append(
                            TextPrimitive(
                                x=cx_col,
                                y=cur_y_col + settings.clue_font_size,
                                text=ln,
                                font_size=settings.clue_font_size,
                                font_family=clue_font_family,
                                bold=False,
                                color=clue_color,
                                anchor="start",
                            )
                        )
                        cur_y_col += line_h
                    cur_y_col += clue_spacing

        _render_side_column("ACROSS", across, 0)
        _render_side_column("DOWN", down, 1)
        return

    # Build a flat stream of renderable blocks: ("header", text) or ("item", [str, ...])
    blocks: list[tuple[str, list[str]]] = []
    for raw_heading, group in (("ACROSS", across), ("DOWN", down)):
        if not group:
            continue
        blocks.append(("header", [_format_heading(raw_heading)]))
        formatted_items: list[str] = [_format_entry_line(e) for e in group]

        if layout_mode == "inline":
            combined = "  •  ".join(formatted_items)
            wrapped = _wrap_text(
                combined,
                max_width_pt=col_w,
                font_size=settings.clue_font_size,
                family=clue_font_family,
                font_dir=font_dir,
            )
            blocks.append(("item", wrapped))
        else:
            for full_line in formatted_items:
                wrapped = _wrap_text(
                    full_line,
                    max_width_pt=col_w,
                    font_size=settings.clue_font_size,
                    family=clue_font_family,
                    font_dir=font_dir,
                )
                blocks.append(("item", wrapped))

    cur_page = pages[-1]
    col_idx = 0
    page_origin_x = content_x
    col_x = page_origin_x
    cur_y = start_y

    def _advance_column():
        nonlocal cur_page, col_idx, page_origin_x, col_x, cur_y
        if col_idx + 1 < num_cols:
            col_idx += 1
            col_x = page_origin_x + col_idx * (col_w + col_gap)
            cur_y = start_y if len(pages) == 1 else top_y
        else:
            cur_page = _new_page(width_pt, height_pt, settings)
            pages.append(cur_page)
            page_origin_x, _ = page_content_x_and_w(
                width_pt,
                settings,
                page_number=start_page_number + len(pages) - 1,
            )
            col_idx = 0
            col_x = page_origin_x
            cur_y = top_y

    for kind, lines in blocks:
        needed_h = header_h if kind == "header" else len(lines) * line_h + clue_spacing
        if cur_y + needed_h > bottom_y:
            _advance_column()

        if kind == "header":
            cur_page.primitives.append(
                TextPrimitive(
                    x=col_x,
                    y=cur_y + settings.clue_font_size * heading_scale,
                    text=lines[0],
                    font_size=settings.clue_font_size * heading_scale,
                    font_family=clue_font_family,
                    bold=True,
                    color=clue_color,
                    anchor="start",
                )
            )
            cur_y += header_h
        else:
            for ln in lines:
                cur_page.primitives.append(
                    TextPrimitive(
                        x=col_x,
                        y=cur_y + settings.clue_font_size,
                        text=ln,
                        font_size=settings.clue_font_size,
                        font_family=clue_font_family,
                        bold=False,
                        color=clue_color,
                        anchor="start",
                    )
                )
                cur_y += line_h
            cur_y += clue_spacing


def build_export_pages(
    puzzle: ExportPuzzleData,
    kind: str,
    settings: ExportSettings,
    font_dir: str = "",
    start_page_number: int = 1,
) -> list[PagePrimitives]:
    """Build unified vector primitives for puzzle, clues, answer_key, or puzzle_with_clues."""
    valid_kinds = {"puzzle", "clues", "answer_key", "puzzle_with_clues"}
    if kind not in valid_kinds:
        raise ValueError(f"Unsupported export kind '{kind}'")

    width_pt, height_pt = resolve_page_dimensions(settings)
    content_x, content_w = page_content_x_and_w(
        width_pt, settings, page_number=start_page_number
    )
    top_y = settings.margin_top
    bottom_y = height_pt - settings.margin_bottom

    page = _new_page(width_pt, height_pt, settings)
    pages = [page]

    cur_y = top_y
    if kind == "answer_key":
        title_text = (
            puzzle.solution_title
            if puzzle.solution_title is not None
            else (f"{puzzle.title} — Answer Key" if puzzle.title else "")
        )
    else:
        title_text = puzzle.title
    if title_text:
        is_answer_key = kind == "answer_key"
        title_font = (
            (settings.solution_title_font_family or settings.title_font_family or settings.font_family)
            if is_answer_key
            else (settings.title_font_family or settings.font_family)
        )
        t_size = (
            (settings.solution_title_font_size if settings.solution_title_font_size is not None else settings.title_font_size)
            if is_answer_key
            else settings.title_font_size
        )
        title_color = (
            (settings.solution_title_color or settings.title_color or settings.ink_color)
            if is_answer_key
            else (settings.title_color or settings.ink_color)
        )
        t_align = (
            (settings.solution_title_alignment or settings.title_alignment or "left")
            if is_answer_key
            else (settings.title_alignment or "left")
        )
        t_gap = float(settings.solution_title_gap if is_answer_key else settings.title_gap)
        if t_align == "center":
            tx = content_x + content_w / 2.0
            t_anchor = "middle"
        elif t_align == "right":
            tx = content_x + content_w
            t_anchor = "end"
        else:
            tx = content_x
            t_anchor = "start"
        page.primitives.append(
            TextPrimitive(
                x=tx,
                y=cur_y + t_size,
                text=title_text,
                font_size=t_size,
                font_family=title_font,
                bold=True,
                color=title_color,
                anchor=t_anchor,
            )
        )
        cur_y += t_size * 1.2 + max(0.0, t_gap)

    avail_h = max(72.0, bottom_y - cur_y)

    if kind == "puzzle":
        _draw_grid(
            page,
            puzzle,
            content_x=content_x,
            content_y=cur_y,
            content_w=content_w,
            max_grid_h=avail_h,
            show_answers=False,
            settings=settings,
        )
    elif kind == "answer_key":
        _draw_grid(
            page,
            puzzle,
            content_x=content_x,
            content_y=cur_y,
            content_w=content_w,
            max_grid_h=avail_h,
            show_answers=True,
            settings=settings,
        )
    elif kind == "clues":
        _draw_clues_flowing(
            pages,
            puzzle,
            width_pt=width_pt,
            height_pt=height_pt,
            content_x=content_x,
            start_y=cur_y,
            content_w=content_w,
            top_y=top_y,
            bottom_y=bottom_y,
            settings=settings,
            font_dir=font_dir,
            start_page_number=start_page_number,
        )
    elif kind == "puzzle_with_clues":
        grid_max_h = avail_h * 0.52
        after_grid_y = _draw_grid(
            page,
            puzzle,
            content_x=content_x,
            content_y=cur_y,
            content_w=content_w,
            max_grid_h=grid_max_h,
            show_answers=False,
            settings=settings,
        )
        _draw_clues_flowing(
            pages,
            puzzle,
            width_pt=width_pt,
            height_pt=height_pt,
            content_x=content_x,
            start_y=after_grid_y + max(0.0, float(settings.puzzle_clue_gap)),
            content_w=content_w,
            top_y=top_y,
            bottom_y=bottom_y,
            settings=settings,
            font_dir=font_dir,
            start_page_number=start_page_number,
        )

    return pages


VALID_SOLUTIONS_PER_PAGE = (1, 2, 4, 6, 8, 9, 12)


def build_solution_pages(
    puzzles: list[ExportPuzzleData],
    settings: ExportSettings,
    *,
    solutions_per_page: int = 4,
    start_page_number: int = 1,
) -> list[PagePrimitives]:
    """Render answer keys packed 1, 2, 4, 6, 8, 9, or 12 per page using unified vector primitives."""
    if not puzzles:
        return []

    per_page = solutions_per_page if solutions_per_page in VALID_SOLUTIONS_PER_PAGE else 4
    grid_layout = {
        1: (1, 1),
        2: (2, 1),
        4: (2, 2),
        6: (3, 2),
        8: (4, 2),
        9: (3, 3),
        12: (4, 3),
    }[per_page]
    n_rows, n_cols = grid_layout

    width_pt, height_pt = resolve_page_dimensions(settings)
    top_y = settings.margin_top
    bottom_y = height_pt - settings.margin_bottom

    header_size = max(10.0, min(settings.title_font_size, 15.0))
    header_h = header_size * 1.7
    gap_x = 10.0 if per_page >= 8 else 16.0
    gap_y = 10.0 if per_page >= 8 else 14.0

    pages: list[PagePrimitives] = []
    for page_offset, chunk_idx in enumerate(range(0, len(puzzles), per_page)):
        content_x, content_w = page_content_x_and_w(
            width_pt, settings, page_number=start_page_number + page_offset
        )
        chunk = puzzles[chunk_idx : chunk_idx + per_page]
        page = _new_page(width_pt, height_pt, settings)
        if chunk_idx == 0:
            page.bookmark = "Solutions"

        heading = "Solutions" if chunk_idx == 0 else "Solutions (cont.)"
        page.primitives.append(
            TextPrimitive(
                x=content_x,
                y=top_y + header_size,
                text=heading,
                font_size=header_size,
                font_family=settings.font_family,
                bold=True,
                color=settings.ink_color,
                anchor="start",
            )
        )

        body_y = top_y + header_h
        body_h = max(72.0, bottom_y - body_y)
        slot_w = (content_w - (n_cols - 1) * gap_x) / n_cols
        slot_h = (body_h - (n_rows - 1) * gap_y) / n_rows
        slot_title_size = (
            min(14.0, float(settings.solution_title_font_size))
            if settings.solution_title_font_size is not None
            else max(7.0, min(11.0, settings.clue_font_size))
        )
        slot_title_gap = max(0.0, float(settings.solution_title_gap))
        slot_title_h = slot_title_size * 1.2 + min(slot_title_gap, slot_h * 0.18)
        slot_title_font = settings.solution_title_font_family or settings.title_font_family or settings.font_family
        slot_title_color = settings.solution_title_color or settings.title_color or settings.ink_color
        slot_title_align = settings.solution_title_alignment or "center"

        slot_settings = ExportSettings(
            **{
                **settings.__dict__,
                "grid_alignment": "center",
                "grid_line_width": max(0.35, settings.grid_line_width * 0.7),
                "border_line_width": max(0.6, settings.border_line_width * 0.7),
            }
        )

        for slot_i, puz in enumerate(chunk):
            r_idx = slot_i // n_cols
            c_idx = slot_i % n_cols
            sx = content_x + c_idx * (slot_w + gap_x)
            sy = body_y + r_idx * (slot_h + gap_y)

            label = (
                puz.solution_title
                if puz.solution_title is not None
                else (puz.title or f"Puzzle {chunk_idx + slot_i + 1}")
            )
            if label:
                if slot_title_align == "left":
                    lx = sx
                    l_anchor = "start"
                elif slot_title_align == "right":
                    lx = sx + slot_w
                    l_anchor = "end"
                else:
                    lx = sx + slot_w / 2.0
                    l_anchor = "middle"
                page.primitives.append(
                    TextPrimitive(
                        x=lx,
                        y=sy + slot_title_size,
                        text=label,
                        font_size=slot_title_size,
                        font_family=slot_title_font,
                        bold=True,
                        color=slot_title_color,
                        anchor=l_anchor,
                    )
                )
            grid_y = sy + (slot_title_h if label else 0.0)
            _draw_grid(
                page,
                puz,
                content_x=sx,
                content_y=grid_y,
                content_w=slot_w,
                max_grid_h=max(36.0, slot_h - (slot_title_h if label else 0.0)),
                show_answers=True,
                settings=slot_settings,
            )

        pages.append(page)

    return pages

