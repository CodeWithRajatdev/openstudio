from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.wordsearch.engine import PuzzleConfig, SizingMode
from app.wordsearch.engine.normalize import NormalizeRules
from app.wordsearch.render import PageLayout


class RulesIn(BaseModel):
    remove_spaces: bool = True
    remove_hyphens: bool = True
    remove_apostrophes: bool = True
    strip_accents: bool = True
    allow_digits: bool = False

    def to_rules(self) -> NormalizeRules:
        return NormalizeRules(**self.model_dump())


class ConfigIn(BaseModel):
    sizing_mode: SizingMode = SizingMode.AUTO
    rows: int = Field(15, ge=1, le=100)
    cols: int = Field(15, ge=1, le=100)
    max_rows: int = Field(40, ge=1, le=100)
    max_cols: int = Field(40, ge=1, le=100)
    horizontal: bool = True
    vertical: bool = True
    diagonal: bool = True
    reverse: bool = False
    attempts_per_size: int = Field(40, ge=1, le=1000)
    density_factor: float = Field(1.8, gt=0.5, le=10)
    normalize: RulesIn = RulesIn()

    def to_config(self, seed: Optional[int] = None) -> PuzzleConfig:
        d = self.model_dump()
        d["normalize"] = self.normalize.to_rules()
        d["seed"] = seed
        return PuzzleConfig(**d)


class LayoutIn(BaseModel):
    page_width: float = Field(215.9, gt=20, le=1000)
    page_height: float = Field(279.4, gt=20, le=1000)
    # Page margins
    margin: float = Field(15.0, ge=0, le=100)
    margin_mode: str = "edges"
    extra_margins: bool = False
    margin_top: float = Field(0.0, ge=0, le=100)
    margin_right: float = Field(0.0, ge=0, le=100)
    margin_bottom: float = Field(0.0, ge=0, le=100)
    margin_left: float = Field(0.0, ge=0, le=100)
    # Puzzle grid
    cell_size: float = Field(9.0, gt=1, le=40)
    min_cell_size: float = Field(3.5, gt=0.5, le=40)
    grid_line_width: float = Field(0.25, ge=0, le=5)
    grid_line_color: str = "#222222"
    cell_color: Optional[str] = None
    border_width: float = Field(0.0, ge=0, le=5)
    border_color: str = "#000000"
    letter_color: str = "#111111"
    letter_size_ratio: float = Field(0.55, gt=0.1, le=1)
    grid_font: str = "Open Sans"
    grid_font_weight: str = "bold"
    grid_font_style: str = "normal"
    uppercase_letters: bool = True
    puzzles_per_page: int = 1
    puzzle_align: str = "center"
    puzzle_valign: str = "top"
    # Title
    title_enabled: bool = True
    title_mode: str = "chapter"
    title_text: str = "Puzzle #PUZZLE_NUMBER"
    title_start_number: int = Field(1, ge=0, le=100000)
    title_font: str = "Open Sans"
    title_size: float = Field(8.0, gt=1, le=40)
    title_weight: str = "bold"
    title_style: str = "normal"
    title_color: Optional[str] = None
    title_align: str = "center"
    title_gap: float = Field(5.0, ge=0, le=100)
    # Clues
    clue_type: str = "columns"
    clue_sort: str = "alpha"
    clue_align: str = "left"
    clue_font: str = "Open Sans"
    clue_font_size: float = Field(4.2, gt=1, le=20)
    clue_size_ratio: Optional[float] = Field(None, gt=0.005, le=0.2)
    clue_weight: str = "normal"
    clue_style: str = "normal"
    clue_color: Optional[str] = None
    clue_line_height: float = Field(1.6, ge=1, le=4)
    clue_columns: int = Field(3, ge=1, le=4)
    clue_uppercase: bool = True
    clue_gap: float = Field(6.0, ge=0, le=100)
    # Solution
    solution_font: Optional[str] = None
    solution_font_weight: Optional[str] = None
    solution_font_style: Optional[str] = None
    solution_letter_size_ratio: Optional[float] = Field(None, gt=0.1, le=1)
    solution_letter_color: Optional[str] = None
    solution_uppercase: Optional[bool] = None
    solution_line_width: Optional[float] = Field(None, ge=0, le=5)
    solution_line_color: Optional[str] = None
    solution_cell_color: Optional[str] = None
    solution_border_width: Optional[float] = Field(None, ge=0, le=5)
    solution_border_color: Optional[str] = None
    solution_title_enabled: bool = True
    solution_title_text: str = "Answer Key: TITLE"
    solution_title_font: Optional[str] = None
    solution_title_size: Optional[float] = Field(None, gt=1, le=40)
    solution_title_weight: Optional[str] = None
    solution_title_style: Optional[str] = None
    solution_title_color: Optional[str] = None
    solution_align: str = "center"
    solution_flow: str = "row"
    highlight_color: str = "#d62839"
    highlight_width: Optional[float] = Field(None, gt=0, le=5)
    # Page furniture
    background: Optional[str] = None
    footer_text: Optional[str] = None
    footer_size: float = Field(3.2, gt=1, le=20)
    page_numbers: bool = False
    page_number_position: str = "right"
    page_number_size: float = Field(3.2, gt=1, le=20)
    page_number_color: str = "#444444"

    def to_layout(self) -> PageLayout:
        return PageLayout(**self.model_dump())


class WordIn(BaseModel):
    id: int
    raw: str = ""
    text: str
    source: Optional[str] = None


class ChapterIn(BaseModel):
    title: str
    words: list[WordIn]
    title_entry: Optional[WordIn] = None


class BankValidateIn(BaseModel):
    chapters: list[ChapterIn]
    rules: RulesIn = RulesIn()
    check_cross_chapter: bool = False
    max_word_length: Optional[int] = Field(None, ge=1, le=200)
    expected_words: Optional[int] = Field(None, ge=1, le=500)


class AnswerItem(BaseModel):
    title: str = ""
    words: list[str]
    seed: Optional[int] = None
    index: Optional[int] = Field(None, ge=0)


class PreviewIn(BaseModel):
    words: list[str]
    title: str = ""
    index: int = Field(0, ge=0)
    page_number: Optional[int] = Field(None, ge=1)
    seed: Optional[int] = None
    config: ConfigIn = ConfigIn()
    layout: LayoutIn = LayoutIn()
    answer_style: str = "rounded_rect"
    solutions_per_page: int = Field(1, ge=1, le=9)
    total_chapters: Optional[int] = Field(None, ge=1)
    extra_puzzles: list[AnswerItem] = []
    solution_items: list[AnswerItem] = []


class PreviewAnswersIn(BaseModel):
    items: list[AnswerItem] = Field(..., min_length=1, max_length=9)
    per_page: int = 4
    style: str = "rounded_rect"
    page_number: Optional[int] = Field(None, ge=1)
    config: ConfigIn = ConfigIn()
    layout: LayoutIn = LayoutIn()


class JobChapter(BaseModel):
    index: int = Field(..., ge=0)
    title: str
    words: list[str]


class JobIn(BaseModel):
    chapters: list[JobChapter] = Field(..., min_length=1)
    config: ConfigIn = ConfigIn()
    layout: LayoutIn = LayoutIn()
    base_seed: int = 0
    seed_overrides: dict[int, int] = {}
    # When set, every chapter must contain exactly this many words (enforced server-side).
    expected_words: Optional[int] = Field(None, ge=1, le=500)


class ExportIn(BaseModel):
    project_name: str = "Word Search Book"
    per_page_answers: int = 4
    answer_style: str = "rounded_rect"
    page_numbers: Optional[bool] = None
    include_answers: bool = True
