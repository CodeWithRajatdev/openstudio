"""Export layout settings and page dimension presets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

POINTS_PER_UNIT: dict[str, float] = {
    "pt": 1.0,
    "in": 72.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
}

PAGE_PRESETS_IN: dict[str, tuple[float, float]] = {
    "letter": (8.5, 11.0),
    "6x9": (6.0, 9.0),
    "8x10": (8.0, 10.0),
    "8.5x8.5": (8.5, 8.5),
}

# A4 in points (210mm x 297mm)
A4_PT: tuple[float, float] = (210.0 * POINTS_PER_UNIT["mm"], 297.0 * POINTS_PER_UNIT["mm"])


@dataclass
class ExportSettings:
    page_size: str = "letter"  # letter | a4 | 6x9 | 8x10 | 8.5x8.5 | custom
    custom_width: Optional[float] = None
    custom_height: Optional[float] = None
    custom_unit: str = "in"  # in | mm | cm | pt
    margin_top: float = 36.0
    margin_bottom: float = 36.0
    margin_left: float = 36.0
    margin_right: float = 36.0
    gutter: float = 0.0
    grid_alignment: str = "center"  # left | center | right
    font_family: str = "Vera"
    title_font_family: Optional[str] = None
    title_font_size: float = 16.0
    title_color: Optional[str] = None
    title_alignment: str = "left"  # left | center | right
    title_gap: float = 10.0
    solution_title_font_family: Optional[str] = None
    solution_title_font_size: Optional[float] = None
    solution_title_color: Optional[str] = None
    solution_title_alignment: str = "center"  # left | center | right
    solution_title_gap: float = 8.0
    clue_font_family: Optional[str] = None
    clue_font_size: float = 9.5
    clue_color: Optional[str] = None
    clue_spacing: float = 2.0
    puzzle_clue_gap: float = 16.0
    clue_layout_mode: str = "columns"  # columns | rows | inline | side_by_side
    clue_heading_style: str = "uppercase"  # uppercase | title | bold
    clue_sort: str = "number"  # number | alphabetical
    number_font_family: Optional[str] = None
    number_font_size: float = 6.5
    number_color: Optional[str] = None
    number_position: str = "top_left"  # top_left | top_right | bottom_left
    letter_font_size: float = 12.0
    capital_letters: bool = True
    solution_font_family: Optional[str] = None
    solution_color: Optional[str] = None
    solution_highlight_style: str = "bold"  # bold | shaded | outline
    grid_line_width: float = 0.75
    border_line_width: float = 1.5
    ink_color: str = "#000000"
    bg_color: str = "#FFFFFF"
    block_color: str = "#000000"
    cell_bg_color: str = "#FFFFFF"
    show_clue_lengths: bool = True
    enumeration_display: str = "formatted"  # formatted | total | none
    clue_capitalization: str = "sentence"  # sentence | title | uppercase | lowercase | as_is
    clue_ending_punctuation: str = "keep"  # keep | period | none
    black_empty_cells: bool = True
    dpi: int = 300


def resolve_page_dimensions(settings: ExportSettings) -> tuple[float, float]:
    """Return (width_pt, height_pt) for the configured page size."""
    key = (settings.page_size or "letter").strip().lower()
    if key == "a4":
        return A4_PT
    if key in PAGE_PRESETS_IN:
        w_in, h_in = PAGE_PRESETS_IN[key]
        return (w_in * 72.0, h_in * 72.0)
    if key == "custom":
        if not settings.custom_width or not settings.custom_height:
            raise ValueError("custom page_size requires custom_width and custom_height")
        unit = (settings.custom_unit or "in").strip().lower()
        factor = POINTS_PER_UNIT.get(unit)
        if factor is None:
            raise ValueError(f"Unsupported unit '{settings.custom_unit}'")
        return (float(settings.custom_width) * factor, float(settings.custom_height) * factor)
    raise ValueError(f"Unsupported page_size '{settings.page_size}'")
