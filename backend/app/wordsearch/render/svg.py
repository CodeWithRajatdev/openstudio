"""Native SVG generation straight from structured puzzle data.

No raster images, no tracing: the grid is a <path>, letters are <text>,
highlights are <rect>/<ellipse>/<line>. Text stays editable; fonts are named
with a CSS fallback stack and embedded in the PDF (see fonts.py).

The same functions produce the browser preview and the PDF pages, so both
always match.
"""
from __future__ import annotations

import math
import random
import re
from typing import Iterable, Optional, Sequence
from xml.sax.saxutils import escape, quoteattr

from app.wordsearch.engine.models import Placement, Puzzle

from .fonts import css_stack, text_width
from .layout import GridStyle, LayoutError, PageLayout, TextStyle

HIGHLIGHT_STYLES = ("rounded_rect", "circle", "line", "highlight")
SHEET_GRIDS = {1: (1, 1), 2: (1, 2), 4: (2, 2), 6: (2, 3), 9: (3, 3)}   # per_page -> (cols, rows)
DEFAULT_PALETTE = ("#d62839",)
MIN_CLUE_SIZE = 2.0      # mm (~5.7 pt); below this the clue list is unreadable
MIN_TITLE_SIZE = 2.5
PLACEHOLDER_RE = re.compile(r"PUZZLE_NUMBER|CHAPTER_TITLE|TITLE")


def _n(x: float) -> str:
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# ------------------------------------------------------------------ titles
def fill_placeholders(template: str, number: int, chapter_title: str = "",
                      title: str = "") -> str:
    """Replace PUZZLE_NUMBER, CHAPTER_TITLE and TITLE. If a placeholder resolves to
    nothing, dangling separators (": - #") at the ends are trimmed."""
    values = {"PUZZLE_NUMBER": str(number), "CHAPTER_TITLE": chapter_title or "",
              "TITLE": title or chapter_title or ""}
    empty = False

    def sub(m):
        nonlocal empty
        v = values[m.group(0)]
        empty = empty or not v
        return v
    out = PLACEHOLDER_RE.sub(sub, template or "")
    if empty:
        out = re.sub(r"^[\s:\-–#|]+|[\s:\-–#|]+$", "", out)
    return out.strip()


def puzzle_number(layout: PageLayout, index: int) -> int:
    return layout.title_start_number + index


def resolve_title(layout: PageLayout, chapter_title: str, index: int) -> str:
    """Title printed above puzzle `index` (0-based chapter position)."""
    if not layout.title_enabled:
        return ""
    if layout.title_mode == "chapter":
        return chapter_title or ""
    return fill_placeholders(layout.title_text, puzzle_number(layout, index), chapter_title)


def resolve_solution_title(layout: PageLayout, chapter_title: str, index: int) -> str:
    if not layout.solution_title_enabled:
        return ""
    shown = resolve_title(layout.with_(title_enabled=True), chapter_title, index)
    return fill_placeholders(layout.solution_title_text, puzzle_number(layout, index),
                             chapter_title, shown)


# ----------------------------------------------------------------- helpers
def _font_attrs(font: str, weight: str, style: str) -> str:
    out = f'font-family={quoteattr(css_stack(font))} font-weight="{escape(weight)}"'
    if style and style != "normal":
        out += f' font-style="{escape(style)}"'
    return out


_ANCHOR = {"left": "start", "center": "middle", "right": "end"}


def _align_x(align: str, x0: float, width: float) -> float:
    return {"left": x0, "center": x0 + width / 2, "right": x0 + width}[align]


def _fit_size(text: str, ts: TextStyle, max_w: float, minimum: float) -> float:
    """Font size for `text` so it fits `max_w` (never larger than requested)."""
    size = ts.size
    w = text_width(text, ts.font, size, ts.weight, ts.style)
    if w > max_w > 0:
        size = size * max_w / w
    return max(size, minimum)


def _text(cls: str, x: float, y: float, text: str, ts: TextStyle, size: float,
          anchor: str) -> str:
    return (f'<text class="{cls}" x="{_n(x)}" y="{_n(y)}" text-anchor="{anchor}" '
            f'{_font_attrs(ts.font, ts.weight, ts.style)} font-size="{_n(size)}" '
            f'fill="{ts.color}">{escape(text)}</text>')


# ---------------------------------------------------------------- highlights
def _tint_hex(color: str, alpha: float = 0.35) -> str:
    """Blend a hex colour against white into an opaque print-safe tint (no alpha/transparency)."""
    s = (color or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return color
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return color
    blend = lambda c: max(0, min(255, round(255 - (255 - c) * alpha)))  # noqa: E731
    return f"#{blend(r):02x}{blend(g):02x}{blend(b):02x}"


def _highlight(p: Placement, cell: float, style: str, color: str,
               width: Optional[float] = None) -> str:
    sx, sy = (p.start_col + 0.5) * cell, (p.start_row + 0.5) * cell
    ex, ey = (p.end_col + 0.5) * cell, (p.end_row + 0.5) * cell
    length = math.hypot(ex - sx, ey - sy)
    angle = math.degrees(math.atan2(ey - sy, ex - sx))
    cx, cy = (sx + ex) / 2, (sy + ey) / 2
    sw = width if width else max(cell * 0.06, 0.2)
    rot = f' transform="rotate({_n(angle)} {_n(cx)} {_n(cy)})"'
    data = (f'data-word={quoteattr(p.original)} data-direction="{p.direction}" '
            f'data-start="{p.start_row},{p.start_col}" data-end="{p.end_row},{p.end_col}"')
    if style == "line":
        return (f'<line x1="{_n(sx)}" y1="{_n(sy)}" x2="{_n(ex)}" y2="{_n(ey)}" '
                f'stroke="{color}" stroke-width="{_n(width if width else cell * 0.12)}" '
                f'stroke-linecap="round" {data}/>')
    if style == "rounded_rect":
        h = cell * 0.84
        w = length + h
        return (f'<rect x="{_n(cx - w / 2)}" y="{_n(cy - h / 2)}" width="{_n(w)}" '
                f'height="{_n(h)}" rx="{_n(h / 2)}" fill="none" stroke="{color}" '
                f'stroke-width="{_n(sw)}"{rot} {data}/>')
    if style == "circle":   # ellipse around the whole word
        ry = cell * 0.46
        rx = length / 2 + cell * 0.5
        return (f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(rx)}" ry="{_n(ry)}" '
                f'fill="none" stroke="{color}" stroke-width="{_n(sw)}"{rot} {data}/>')
    if style == "highlight":
        h = cell * 0.86
        w = length + cell * 0.9
        return (f'<rect x="{_n(cx - w / 2)}" y="{_n(cy - h / 2)}" width="{_n(w)}" '
                f'height="{_n(h)}" fill="{_tint_hex(color, 0.35)}" stroke="none"'
                f'{rot} {data}/>')
    raise ValueError(f"unknown highlight style {style!r}; choose from {HIGHLIGHT_STYLES}")


# ---------------------------------------------------------------- grid group
def _grid_fragment(puzzle: Puzzle, cell: float, gs: GridStyle,
                   highlight_style: Optional[str] = None,
                   palette: Iterable[str] = DEFAULT_PALETTE,
                   highlight_width: Optional[float] = None) -> str:
    """SVG elements for the grid with origin (0,0). Size = cols*cell x rows*cell."""
    w, h = puzzle.cols * cell, puzzle.rows * cell
    parts: list[str] = []
    if gs.cell_color:
        parts.append(f'<rect class="cell-fill" width="{_n(w)}" height="{_n(h)}" '
                     f'fill="{gs.cell_color}"/>')
    # Grid lines as one path.
    if gs.cell_line_width > 0:
        d = []
        for r in range(puzzle.rows + 1):
            d.append(f"M0 {_n(r * cell)}H{_n(w)}")
        for c in range(puzzle.cols + 1):
            d.append(f"M{_n(c * cell)} 0V{_n(h)}")
        parts.append(f'<path class="grid-lines" d="{"".join(d)}" fill="none" '
                     f'stroke="{gs.cell_line_color}" '
                     f'stroke-width="{_n(gs.cell_line_width)}" stroke-linecap="square"/>')
    # Highlights first so letters stay readable on top.
    if highlight_style:
        colors = list(palette) or list(DEFAULT_PALETTE)
        hl = [_highlight(p, cell, highlight_style, colors[i % len(colors)], highlight_width)
              for i, p in enumerate(puzzle.placements)]
        parts.append('<g class="answer-highlights">' + "".join(hl) + "</g>")
    # Letters.
    fs = cell * gs.size_ratio
    letters = []
    for r in range(puzzle.rows):
        for c in range(puzzle.cols):
            ch = puzzle.grid[r][c]
            ch = ch.upper() if gs.uppercase else ch.lower()
            letters.append(
                f'<text x="{_n((c + 0.5) * cell)}" y="{_n((r + 0.5) * cell + fs * 0.35)}">'
                f'{escape(ch)}</text>')
    parts.append(
        f'<g class="grid-letters" {_font_attrs(gs.font, gs.weight, gs.style)} '
        f'font-size="{_n(fs)}" text-anchor="middle" fill="{gs.letter_color}">'
        + "".join(letters) + "</g>")
    if gs.border_width > 0:
        parts.append(f'<rect class="grid-border" width="{_n(w)}" height="{_n(h)}" fill="none" '
                     f'stroke="{gs.border_color}" stroke-width="{_n(gs.border_width)}"/>')
    return "".join(parts)


def _svg_open(layout: PageLayout, title: str, desc: str) -> str:
    W, H = layout.page_width, layout.page_height
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(W)}mm" height="{_n(H)}mm" '
            f'viewBox="0 0 {_n(W)} {_n(H)}">'
            f'<title>{escape(title)}</title><desc>{escape(desc)}</desc>')
    if layout.background:
        head += f'<rect width="{_n(W)}" height="{_n(H)}" fill="{layout.background}"/>'
    return head


def _furniture(layout: PageLayout, page_number: Optional[int]) -> str:
    """Footer text and page number, inside the bottom of the printable area."""
    out = []
    W = layout.page_width
    base = layout.page_height - layout.mb
    if layout.footer_text:
        out.append(f'<text class="footer" x="{_n(W / 2)}" y="{_n(base - layout.footer_size * 0.3)}" '
                   f'text-anchor="middle" font-family={quoteattr(css_stack(layout.clue_font))} '
                   f'font-size="{_n(layout.footer_size)}" fill="#555">'
                   f'{escape(layout.footer_text)}</text>')
    if layout.page_numbers and page_number is not None:
        pos = layout.page_number_position
        if pos == "outer":
            pos = "right" if page_number % 2 == 1 else "left"
        x = {"center": W / 2, "right": W - layout.mr, "left": layout.ml}[pos]
        out.append(f'<text class="page-number" x="{_n(x)}" '
                   f'y="{_n(base - layout.page_number_size * 0.3)}" text-anchor="{_ANCHOR[pos]}" '
                   f'font-family={quoteattr(css_stack(layout.clue_font))} '
                   f'font-size="{_n(layout.page_number_size)}" '
                   f'fill="{layout.page_number_color}">{page_number}</text>')
    return "".join(out)


# ----------------------------------------------------------------- clue list
def sort_clues(words: Sequence[str], how: str, seed: int = 0) -> list[str]:
    words = list(words)
    if how == "alpha":
        return sorted(words, key=lambda w: w.upper())
    if how == "short_long":
        return sorted(words, key=lambda w: (len(w), w.upper()))
    if how == "long_short":
        return sorted(words, key=lambda w: (-len(w), w.upper()))
    if how == "random":       # reproducible: seeded by the puzzle seed
        out = sorted(words, key=lambda w: w.upper())
        random.Random(f"clues:{seed}").shuffle(out)
        return out
    return words              # "file": keep the given order


def _clue_block(words: list[str], layout: PageLayout, avail_w: float, x0: float, y0: float,
                scale: float = 1.0):
    """Returns (svg, height). Shrinks the font (never clips) if text is too wide."""
    ts = layout.clue_style_()
    if layout.clue_uppercase:
        words = [w.upper() for w in words]
    if not words:
        return "", 0.0
    fs = ts.size * scale
    measure = lambda w, s: text_width(w, ts.font, s, ts.weight, ts.style)  # noqa: E731
    items: list[tuple[float, float, str, str]] = []     # x, y, text, anchor
    if layout.clue_type == "inline":
        gap_em = 1.4
        longest = max(measure(w, fs) for w in words)
        if longest > avail_w:
            fs *= avail_w / longest
        if fs < MIN_CLUE_SIZE:
            raise LayoutError("A clue is too long for the page width.")
        gap = fs * gap_em
        lines: list[list[tuple[str, float]]] = [[]]
        used = 0.0
        for w in words:
            ww = measure(w, fs)
            need = ww if not lines[-1] else used + gap + ww
            if lines[-1] and need > avail_w:
                lines.append([])
                used = ww
            else:
                used = need
            lines[-1].append((w, ww))
        lh = fs * layout.clue_line_height
        for r, line in enumerate(lines):
            line_w = sum(ww for _, ww in line) + gap * (len(line) - 1)
            x = x0 + {"left": 0, "center": (avail_w - line_w) / 2,
                      "right": avail_w - line_w}[layout.clue_align]
            for w, ww in line:
                items.append((x, y0 + fs + r * lh, w, "start"))
                x += ww + gap
        height = len(lines) * lh
    else:
        k = layout.clue_columns
        col_w = avail_w / k
        rows = math.ceil(len(words) / k)
        longest = max(measure(w, fs) for w in words)
        room = col_w - min(2.0, col_w * 0.08)
        if longest > room:
            fs *= room / longest
        if fs < MIN_CLUE_SIZE:
            longest_chars = max(len(w) for w in words)
            raise LayoutError(
                f"Clue text too wide for {k} column(s) (longest entry has {longest_chars} "
                "characters). Use fewer clue columns, a smaller clue font or a wider page.")
        lh = fs * layout.clue_line_height
        anchor = _ANCHOR[layout.clue_align]
        for i, w in enumerate(words):
            if layout.clue_type == "rows":
                row, col = divmod(i, k)
            else:
                col, row = divmod(i, rows)
            x = _align_x(layout.clue_align, x0 + col * col_w, col_w)
            items.append((x, y0 + fs + row * lh, w, anchor))
        height = rows * lh
    svg = (f'<g class="clue-list" {_font_attrs(ts.font, ts.weight, ts.style)} '
           f'font-size="{_n(fs)}" fill="{ts.color}" data-font-size="{_n(fs)}">'
           + "".join(f'<text x="{_n(x)}" y="{_n(y)}"'
                     f'{"" if a == "start" else f" text-anchor={chr(34)}{a}{chr(34)}"}>'
                     f'{escape(w)}</text>' for x, y, w, a in items)
           + "</g>")
    return svg, height


# ------------------------------------------------------------- puzzle block
def _puzzle_block(puzzle: Puzzle, title: str, words: list[str], layout: PageLayout,
                  bx: float, by: float, bw: float, bh: float) -> str:
    """Title + grid + clue list inside the box (bx, by, bw, bh)."""
    ts = layout.title_style_()
    t_size = _fit_size(title, ts, bw, MIN_TITLE_SIZE) if title else 0.0
    title_h = (t_size * 1.2 + layout.title_gap) if title else 0.0
    gap = layout.clue_gap if words else 0.0
    gs = layout.puzzle_grid()
    inset = gs.border_width / 2
    fit = None
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):   # clue font shrinks only if the grid can't fit
        _, clue_h = _clue_block(words, layout, bw, 0, 0, scale)
        cell = min(layout.cell_size, (bw - 2 * inset) / puzzle.cols)
        while cell >= layout.min_cell_size:
            if title_h + puzzle.rows * cell + 2 * inset + gap + clue_h <= bh:
                fit = (cell, scale, clue_h)
                break
            cell -= 0.25
        if fit:
            break
    if not fit:
        raise LayoutError(
            f"Puzzle {puzzle.puzzle_id} ({puzzle.rows}x{puzzle.cols}, {len(words)} clues) "
            "does not fit the page at the minimum cell size. Use a larger page, "
            "smaller margins, fewer puzzles per page, more clue columns, or a smaller grid.")
    cell, scale, clue_h = fit
    grid_w, grid_h = puzzle.cols * cell + 2 * inset, puzzle.rows * cell + 2 * inset
    block_h = title_h + grid_h + gap + clue_h
    oy = by + {"top": 0.0, "middle": (bh - block_h) / 2,
               "bottom": bh - block_h}[layout.puzzle_valign]
    out = []
    if title:
        out.append(_text("title", _align_x(ts.align, bx, bw), oy + t_size, title, ts, t_size,
                         _ANCHOR[ts.align]))
    gx = {"left": bx, "center": bx + (bw - grid_w) / 2,
          "right": bx + bw - grid_w}[layout.puzzle_align] + inset
    gy = oy + title_h + inset
    out.append(f'<g class="grid" data-cell="{_n(cell)}" transform="translate({_n(gx)} {_n(gy)})">'
               f'{_grid_fragment(puzzle, cell, gs)}</g>')
    clue_svg, _ = _clue_block(words, layout, bw, bx, oy + title_h + grid_h + gap, scale)
    out.append(clue_svg)
    return "".join(out)


def _tiles(n: int, layout: PageLayout, per_page: int, cols: int, rows: int, gutter: float,
           flow: str = "row"):
    area_w, area_h = layout.content_width, layout.content_height
    tile_w = (area_w - gutter * (cols - 1)) / cols
    tile_h = (area_h - gutter * (rows - 1)) / rows
    for i in range(n):
        if flow == "column":
            c, r = divmod(i, rows)
        else:
            r, c = divmod(i, cols)
        yield (layout.ml + c * (tile_w + gutter), layout.mt + r * (tile_h + gutter),
               tile_w, tile_h)


def _puzzle_grid_shape(layout: PageLayout, per_page: int) -> tuple[int, int]:
    if per_page == 1:
        return 1, 1
    if per_page == 2:
        return (2, 1) if layout.page_width > layout.page_height else (1, 2)
    return 2, 2


def _clues_for(puzzle: Puzzle, layout: PageLayout, clue_words: Optional[list[str]]):
    if clue_words is not None:
        return list(clue_words)
    return sort_clues([p.original for p in puzzle.placements], layout.clue_sort, puzzle.seed)


# ------------------------------------------------------------- puzzle page
def render_puzzle_page(items: Sequence[tuple], layout: Optional[PageLayout] = None,
                       page_number: Optional[int] = None) -> str:
    """One book page with up to `layout.puzzles_per_page` puzzles.

    items: (puzzle, chapter_title, index[, clue_words]) - index is the 0-based chapter
    position used for PUZZLE_NUMBER.
    """
    layout = layout or PageLayout()
    layout.validate()
    per = layout.puzzles_per_page
    if not items:
        raise ValueError("no puzzles supplied")
    if len(items) > per:
        raise ValueError(f"{len(items)} puzzles do not fit {per} per page")
    cols, rows = _puzzle_grid_shape(layout, per)
    gutter = 8.0 if per > 1 else 0.0
    first = items[0][0]
    out = [_svg_open(layout, resolve_title(layout, items[0][1], items[0][2]) or
                     f"Puzzle {first.puzzle_id}",
                     f"Word search page, {len(items)} puzzle(s), engine {first.engine_version}")]
    for it, (tx, ty, tw, th) in zip(items, _tiles(len(items), layout, per, cols, rows, gutter)):
        puz, chapter_title, index = it[0], it[1], it[2]
        clue_words = it[3] if len(it) > 3 else None
        out.append(f'<g class="puzzle" data-puzzle-id={quoteattr(puz.puzzle_id)} '
                   f'data-rows="{puz.rows}" data-cols="{puz.cols}" data-seed="{puz.seed}">')
        out.append(_puzzle_block(puz, resolve_title(layout, chapter_title, index),
                                 _clues_for(puz, layout, clue_words), layout, tx, ty, tw, th))
        out.append("</g>")
    out.append(_furniture(layout, page_number))
    out.append("</svg>")
    return "".join(out)


def render_puzzle_svg(puzzle: Puzzle, title: str = "", layout: Optional[PageLayout] = None,
                      clue_words: Optional[list[str]] = None, index: int = 0,
                      page_number: Optional[int] = None) -> str:
    """A full page holding just this puzzle (individual SVG export)."""
    layout = (layout or PageLayout()).with_(puzzles_per_page=1)
    return render_puzzle_page([(puzzle, title, index, clue_words)], layout, page_number)


# --------------------------------------------------------------- answer keys
def render_answer_key_svg(puzzle: Puzzle, title: str = "",
                          layout: Optional[PageLayout] = None,
                          style: str = "rounded_rect",
                          palette: Optional[Iterable[str]] = None, index: int = 0,
                          page_number: Optional[int] = None) -> str:
    """One answer-key page for one puzzle."""
    return render_answer_key_page([(puzzle, title, index)], 1, layout, style, palette,
                                  page_number)


def render_answer_key_page(items: Sequence[tuple], per_page: int = 1,
                           layout: Optional[PageLayout] = None,
                           style: str = "rounded_rect",
                           palette: Optional[Iterable[str]] = None,
                           page_number: Optional[int] = None) -> str:
    """One page holding up to `per_page` (1, 2, 4, 6 or 9) answer keys.
    items: (puzzle, chapter_title[, index]); index defaults to the position."""
    layout = layout or PageLayout()
    layout.validate()
    if per_page not in SHEET_GRIDS:
        raise ValueError(f"per_page must be one of {sorted(SHEET_GRIDS)}")
    if style not in HIGHLIGHT_STYLES:
        raise ValueError(f"unknown highlight style {style!r}; choose from {HIGHLIGHT_STYLES}")
    if not items:
        raise ValueError("no puzzles supplied")
    if len(items) > per_page:
        raise ValueError(f"{len(items)} puzzles do not fit {per_page} per page")
    palette = list(palette) if palette else [layout.highlight_color]

    cols, rows = SHEET_GRIDS[per_page]
    gutter = 8.0 if per_page > 1 else 0.0
    ts = layout.solution_title_style_(per_page)
    gs = layout.solution_grid()
    inset = gs.border_width / 2

    out = [_svg_open(layout, "Answer key",
                     f"{len(items)} answer key(s), style {style}, {per_page} per page")]
    tiles = _tiles(len(items), layout, per_page, cols, rows, gutter, layout.solution_flow)
    for n, (it, (tx, ty, tile_w, tile_h)) in enumerate(zip(items, tiles)):
        puz, chapter_title = it[0], it[1]
        index = it[2] if len(it) > 2 else n
        label = resolve_solution_title(layout, chapter_title, index)
        size = _fit_size(label, ts, tile_w, MIN_TITLE_SIZE * 0.8) if label else 0.0
        label_h = size * 1.7 if label else 0.0
        cell = min(layout.cell_size, (tile_w - 2 * inset) / puz.cols,
                   (tile_h - label_h - 2 * inset) / puz.rows)
        if cell < layout.min_cell_size * 0.6:
            raise LayoutError(
                f"Puzzle {puz.puzzle_id} is too large for {per_page} answer key(s) per page.")
        gw = puz.cols * cell + 2 * inset
        if label:
            out.append(_text("key-title", _align_x(ts.align, tx, tile_w), ty + size, label, ts,
                             size, _ANCHOR[ts.align]))
        gx = {"left": tx, "center": tx + (tile_w - gw) / 2,
              "right": tx + tile_w - gw}[layout.solution_align] + inset
        out.append(f'<g class="answer-grid" data-puzzle-id={quoteattr(puz.puzzle_id)} '
                   f'transform="translate({_n(gx)} {_n(ty + label_h + inset)})">'
                   f'{_grid_fragment(puz, cell, gs, style, palette, layout.highlight_width)}</g>')
    out.append(_furniture(layout, page_number))
    out.append("</svg>")
    return "".join(out)


def render_answer_key_pages(items: Sequence[tuple], per_page: int = 1,
                            layout: Optional[PageLayout] = None,
                            style: str = "rounded_rect") -> list[str]:
    """Paginate any number of puzzles into answer-key pages."""
    items = [it if len(it) > 2 else (it[0], it[1], i) for i, it in enumerate(items)]
    return [render_answer_key_page(items[i:i + per_page], per_page, layout, style)
            for i in range(0, len(items), per_page)]
