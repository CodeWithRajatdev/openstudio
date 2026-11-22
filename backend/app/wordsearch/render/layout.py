from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


class LayoutError(ValueError):
    """Content cannot fit the page with the requested settings."""


ALIGNS = ("left", "center", "right")
VALIGNS = ("top", "middle", "bottom")
CLUE_TYPES = ("columns", "rows", "inline")
CLUE_SORTS = ("alpha", "short_long", "long_short", "random", "file")
TITLE_MODES = ("chapter", "custom")
PAGE_NUMBER_POSITIONS = ("center", "outer", "right", "left")
PUZZLES_PER_PAGE = (1, 2, 4)
MARGIN_MODES = ("edges", "kdp")


@dataclass(frozen=True)
class GridStyle:
    """Appearance of one grid (puzzle or solution). Lengths in mm."""
    font: str
    weight: str
    style: str
    size_ratio: float
    letter_color: str
    uppercase: bool
    cell_line_width: float
    cell_line_color: str
    cell_color: Optional[str]
    border_width: float
    border_color: str


@dataclass(frozen=True)
class TextStyle:
    font: str
    size: float
    weight: str
    style: str
    color: str
    align: str


@dataclass
class PageLayout:
    """All lengths are millimetres; the SVG viewBox uses the same units.

    Defaults reproduce the original output; the UI sends its own defaults
    (Open Sans, BookBolt-style) explicitly.
    """
    page_width: float = 215.9     # US Letter
    page_height: float = 279.4
    # ---- page settings: paper edge + optional additional margins per side
    margin: float = 15.0          # distance from every paper edge ("paper edges")
    # "edges": margins measured from the paper edges as entered.
    # "kdp":   Amazon KDP minimums are applied per page (inside/gutter margin by page
    #          count, mirrored on left/right pages); `margin` is used where it is larger.
    margin_mode: str = "edges"
    extra_margins: bool = False   # "Set additional margins"
    margin_top: float = 0.0       # added to `margin` when extra_margins is on
    margin_right: float = 0.0
    margin_bottom: float = 0.0
    margin_left: float = 0.0
    # ---- puzzle grid
    cell_size: float = 9.0        # maximum; shrinks automatically to fit
    min_cell_size: float = 3.5
    grid_line_width: float = 0.25          # cell outline width
    grid_line_color: str = "#222222"       # cell outline colour
    cell_color: Optional[str] = None       # cell fill; None = transparent
    border_width: float = 0.0              # outer border (0 = cell outline only)
    border_color: str = "#000000"
    letter_color: str = "#111111"
    letter_size_ratio: float = 0.55   # font size as a fraction of the cell
    grid_font: str = "Open Sans"
    grid_font_weight: str = "bold"
    grid_font_style: str = "normal"
    uppercase_letters: bool = True
    puzzles_per_page: int = 1
    puzzle_align: str = "center"           # horizontal position of the grid
    puzzle_valign: str = "top"             # vertical position of the whole block
    # ---- title
    title_enabled: bool = True
    title_mode: str = "chapter"            # chapter title from the file | custom text
    title_text: str = "Puzzle #PUZZLE_NUMBER"
    title_start_number: int = 1
    title_font: str = "Open Sans"
    title_size: float = 8.0
    title_weight: str = "bold"
    title_style: str = "normal"
    title_color: Optional[str] = None      # None = letter_color
    title_align: str = "center"
    title_gap: float = 5.0                 # gap between title and puzzle grid (mm)
    # ---- clues (word list)
    clue_type: str = "columns"
    clue_sort: str = "alpha"
    clue_align: str = "left"
    clue_font: str = "Open Sans"
    clue_font_size: float = 4.2
    clue_size_ratio: Optional[float] = None   # if set: font size = ratio x min(page side)
    clue_weight: str = "normal"
    clue_style: str = "normal"
    clue_color: Optional[str] = None       # None = letter_color
    clue_line_height: float = 1.6     # multiple of font size
    clue_columns: int = 3             # 1-4
    clue_uppercase: bool = True
    clue_gap: float = 6.0                  # gap between puzzle grid and clue list (mm)
    # ---- solution (None = same as the puzzle)
    solution_font: Optional[str] = None
    solution_font_weight: Optional[str] = None
    solution_font_style: Optional[str] = None
    solution_letter_size_ratio: Optional[float] = None
    solution_letter_color: Optional[str] = None
    solution_uppercase: Optional[bool] = None
    solution_line_width: Optional[float] = None
    solution_line_color: Optional[str] = None
    solution_cell_color: Optional[str] = None
    solution_border_width: Optional[float] = None
    solution_border_color: Optional[str] = None
    solution_title_enabled: bool = True
    solution_title_text: str = "Answer Key: TITLE"
    solution_title_font: Optional[str] = None
    solution_title_size: Optional[float] = None      # None = scaled from title_size
    solution_title_weight: Optional[str] = None
    solution_title_style: Optional[str] = None
    solution_title_color: Optional[str] = None
    solution_align: str = "center"
    solution_flow: str = "row"             # fill order of tiles on a page: row | column
    highlight_color: str = "#d62839"
    highlight_width: Optional[float] = None   # outline stroke (mm); None = 6% of a cell
    # ---- page furniture
    background: str | None = None     # e.g. "#ffffff"; None = transparent
    footer_text: str | None = None
    footer_size: float = 3.2
    page_numbers: bool = False        # drawn inside the SVG when a page number is given
    page_number_position: str = "right"
    page_number_size: float = 3.2
    page_number_color: str = "#444444"

    # ------------------------------------------------------------ derived
    @property
    def mt(self) -> float:
        return self.margin + (self.margin_top if self.extra_margins else 0.0)

    @property
    def mr(self) -> float:
        return self.margin + (self.margin_right if self.extra_margins else 0.0)

    @property
    def mb(self) -> float:
        return self.margin + (self.margin_bottom if self.extra_margins else 0.0)

    @property
    def ml(self) -> float:
        return self.margin + (self.margin_left if self.extra_margins else 0.0)

    @property
    def content_width(self) -> float:
        return self.page_width - self.ml - self.mr

    @property
    def content_height(self) -> float:
        """Printable height; reserves a strip at the bottom for footer/page number."""
        reserve = 0.0
        if self.footer_text or self.page_numbers:
            reserve = max(self.footer_size, self.page_number_size) * 1.8
        return self.page_height - self.mt - self.mb - reserve

    @property
    def clue_size(self) -> float:
        if self.clue_size_ratio:
            return self.clue_size_ratio * min(self.page_width, self.page_height)
        return self.clue_font_size

    def puzzle_grid(self) -> GridStyle:
        return GridStyle(self.grid_font, self.grid_font_weight, self.grid_font_style,
                         self.letter_size_ratio, self.letter_color, self.uppercase_letters,
                         self.grid_line_width, self.grid_line_color, self.cell_color,
                         self.border_width, self.border_color)

    def solution_grid(self) -> GridStyle:
        p = self.puzzle_grid()
        pick = lambda v, d: d if v is None else v   # noqa: E731
        return GridStyle(pick(self.solution_font, p.font),
                         pick(self.solution_font_weight, p.weight),
                         pick(self.solution_font_style, p.style),
                         pick(self.solution_letter_size_ratio, p.size_ratio),
                         pick(self.solution_letter_color, p.letter_color),
                         pick(self.solution_uppercase, p.uppercase),
                         pick(self.solution_line_width, p.cell_line_width),
                         pick(self.solution_line_color, p.cell_line_color),
                         pick(self.solution_cell_color, p.cell_color),
                         pick(self.solution_border_width, p.border_width),
                         pick(self.solution_border_color, p.border_color))

    def title_style_(self) -> TextStyle:
        return TextStyle(self.title_font, self.title_size, self.title_weight, self.title_style,
                         self.title_color or self.letter_color, self.title_align)

    def solution_title_style_(self, per_page: int) -> TextStyle:
        base = self.title_size if per_page == 1 else max(self.title_size * 0.55, 3.2)
        return TextStyle(self.solution_title_font or self.title_font,
                         self.solution_title_size or base,
                         self.solution_title_weight or self.title_weight,
                         self.solution_title_style or self.title_style,
                         self.solution_title_color or self.title_color or self.letter_color,
                         self.solution_align)

    def clue_style_(self) -> TextStyle:
        return TextStyle(self.clue_font, self.clue_size, self.clue_weight, self.clue_style,
                         self.clue_color or self.letter_color, self.clue_align)

    def with_(self, **kw) -> "PageLayout":
        return replace(self, **kw)

    def validate(self) -> None:
        if not 1 <= self.clue_columns <= 4:
            raise LayoutError("clue_columns must be between 1 and 4")
        if min(self.margin, self.margin_top, self.margin_right, self.margin_bottom,
               self.margin_left) < 0:
            raise LayoutError("margins cannot be negative")
        if self.title_gap < 0 or self.clue_gap < 0:
            raise LayoutError("title_gap and clue_gap cannot be negative")
        if self.content_width <= 10 or self.content_height <= 10:
            raise LayoutError("margins leave no printable area")
        if self.cell_size < self.min_cell_size:
            raise LayoutError("cell_size is smaller than min_cell_size")
        for name, val, allowed in (
                ("puzzle_align", self.puzzle_align, ALIGNS),
                ("puzzle_valign", self.puzzle_valign, VALIGNS),
                ("title_align", self.title_align, ALIGNS),
                ("clue_align", self.clue_align, ALIGNS),
                ("solution_align", self.solution_align, ALIGNS),
                ("clue_type", self.clue_type, CLUE_TYPES),
                ("clue_sort", self.clue_sort, CLUE_SORTS),
                ("title_mode", self.title_mode, TITLE_MODES),
                ("page_number_position", self.page_number_position, PAGE_NUMBER_POSITIONS),
                ("solution_flow", self.solution_flow, ("row", "column")),
                ("margin_mode", self.margin_mode, MARGIN_MODES),
                ("puzzles_per_page", self.puzzles_per_page, PUZZLES_PER_PAGE)):
            if val not in allowed:
                raise LayoutError(f"{name} must be one of {allowed} (got {val!r})")
