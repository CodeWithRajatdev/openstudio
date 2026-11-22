from typing import Optional

from pydantic import BaseModel, Field


class EngineSettingsIn(BaseModel):
    rows: Optional[int] = Field(None, ge=3, le=60)
    cols: Optional[int] = Field(None, ge=3, le=60)
    max_size: int = Field(40, ge=5, le=60)
    seed: int = 0
    attempts_per_size: int = Field(4, ge=1, le=20)
    polish_attempts: int = Field(3, ge=0, le=20)
    max_nodes_per_attempt: int = Field(3000, ge=100, le=50000)
    branch_factor: int = Field(4, ge=1, le=10)
    time_limit_s: float = Field(20, ge=1, le=300)
    symmetry: str = Field("off", pattern="^(off|preferred)$")
    min_word_length: int = Field(3, ge=2, le=10)
    strategy: str = Field("auto", pattern="^(auto|longest|crossable|random)$")


class GenerateIn(BaseModel):
    words: list[str] = Field(..., min_length=1, max_length=200)
    settings: EngineSettingsIn = EngineSettingsIn()


class PasteImportIn(BaseModel):
    text: str = Field(..., min_length=1)
    collection_name: Optional[str] = None
    language: str = Field("en", min_length=2, max_length=16)
    min_word_length: int = Field(3, ge=2, le=10)
    max_word_length: int = Field(30, ge=5, le=60)
    expected_words_per_chapter: Optional[int] = Field(None, ge=1, le=200)
    grid_rows: Optional[int] = Field(None, ge=3, le=60)
    grid_cols: Optional[int] = Field(None, ge=3, le=60)
    max_grid_size: int = Field(40, ge=5, le=60)


class CommitImportIn(BaseModel):
    collection_id: Optional[int] = None


class CollectionCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    language: str = Field("en", min_length=2, max_length=16)


class ClueGenerateIn(BaseModel):
    collection_id: Optional[int] = None
    word_ids: Optional[list[int]] = None
    mode: str = Field("hybrid", pattern="^(automatic|manual|hybrid)$")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    regenerate: bool = False
    verify: bool = False
    age_group: str = Field("general", min_length=1, max_length=64)


class ClueCreateIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    status: str = Field("approved", pattern="^(approved|draft|needs_review|rejected)$")


class ClueUpdateIn(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=300)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    status: Optional[str] = Field(None, pattern="^(approved|draft|needs_review|rejected)$")


class BulkApproveCluesIn(BaseModel):
    clue_ids: Optional[list[int]] = None
    collection_id: Optional[int] = None


class WordClueRegenerateIn(BaseModel):
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    count: int = Field(3, ge=2, le=3)
    verify: bool = False
    age_group: str = Field("general", min_length=1, max_length=64)
    mode: str = Field("hybrid", pattern="^(automatic|manual|hybrid)$")


class WordClueSelectIn(BaseModel):
    clue_id: int


class ExportSettingsIn(BaseModel):
    page_size: str = Field("letter", pattern="^(letter|a4|6x9|8x10|8\\.5x8\\.5|custom)$")
    custom_width: Optional[float] = Field(None, gt=0)
    custom_height: Optional[float] = Field(None, gt=0)
    custom_unit: str = Field("in", pattern="^(in|mm|cm|pt)$")
    margin_top: float = Field(36.0, ge=0, le=200)
    margin_bottom: float = Field(36.0, ge=0, le=200)
    margin_left: float = Field(36.0, ge=0, le=200)
    margin_right: float = Field(36.0, ge=0, le=200)
    gutter: float = Field(0.0, ge=0, le=100)
    grid_alignment: str = Field("center", pattern="^(left|center|right)$")
    font_family: str = "Vera"
    title_font_family: Optional[str] = None
    title_font_size: float = Field(16.0, ge=6, le=48)
    title_color: Optional[str] = None
    title_alignment: str = Field("left", pattern="^(left|center|right)$")
    title_gap: float = Field(10.0, ge=0, le=72)
    solution_title_font_family: Optional[str] = None
    solution_title_font_size: Optional[float] = Field(None, ge=6, le=48)
    solution_title_color: Optional[str] = None
    solution_title_alignment: str = Field("center", pattern="^(left|center|right)$")
    solution_title_gap: float = Field(8.0, ge=0, le=72)
    clue_font_family: Optional[str] = None
    clue_font_size: float = Field(9.5, ge=5, le=24)
    clue_color: Optional[str] = None
    clue_spacing: float = Field(2.0, ge=0, le=24)
    puzzle_clue_gap: float = Field(16.0, ge=0, le=96)
    clue_layout_mode: str = Field("columns", pattern="^(columns|rows|inline|side_by_side)$")
    clue_heading_style: str = Field("uppercase", pattern="^(uppercase|title|bold)$")
    clue_sort: str = Field("number", pattern="^(number|alphabetical)$")
    number_font_family: Optional[str] = None
    number_font_size: float = Field(6.5, ge=4, le=16)
    number_color: Optional[str] = None
    number_position: str = Field("top_left", pattern="^(top_left|top_right|bottom_left)$")
    letter_font_size: float = Field(12.0, ge=6, le=32)
    capital_letters: bool = True
    solution_font_family: Optional[str] = None
    solution_color: Optional[str] = None
    solution_highlight_style: str = Field("bold", pattern="^(bold|shaded|outline)$")
    grid_line_width: float = Field(0.75, ge=0.1, le=5.0)
    border_line_width: float = Field(1.5, ge=0.0, le=8.0)
    ink_color: str = "#000000"
    bg_color: str = "#FFFFFF"
    block_color: str = "#000000"
    cell_bg_color: str = "#FFFFFF"
    show_clue_lengths: bool = True
    enumeration_display: str = Field("formatted", pattern="^(formatted|total|none)$")
    clue_capitalization: str = Field("sentence", pattern="^(sentence|title|uppercase|lowercase|as_is|keep)$")
    clue_ending_punctuation: str = Field("keep", pattern="^(keep|period|none|as_is)$")
    black_empty_cells: bool = True
    dpi: int = Field(300, ge=72, le=600)


class ExportEntryIn(BaseModel):
    number: int = Field(..., ge=1)
    direction: str = Field(..., pattern="^(A|D)$")
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)
    answer: str = Field(..., min_length=1)
    clue: str = ""
    display: Optional[str] = None


class StatelessExportIn(BaseModel):
    title: str = "Crossword"
    rows: int = Field(..., ge=1, le=60)
    cols: int = Field(..., ge=1, le=60)
    grid: list[str]
    entries: list[ExportEntryIn]
    kind: str = Field("puzzle", pattern="^(puzzle|clues|answer_key|puzzle_with_clues)$")
    format: str = Field("svg", pattern="^(svg|pdf|png)$")
    page: int = Field(0, ge=0)
    settings: ExportSettingsIn = ExportSettingsIn()


class PuzzleGenerateIn(BaseModel):
    collection_id: int
    title: Optional[str] = None
    clue_mode: str = Field("hybrid", pattern="^(automatic|manual|hybrid)$")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    min_density: float = Field(0.15, ge=0.0, le=1.0)
    min_crossings: Optional[int] = Field(None, ge=0, le=100)
    auto_retry: bool = False
    max_retries: int = Field(3, ge=0, le=10)
    settings: EngineSettingsIn = EngineSettingsIn()


class PuzzleEntryClueEditIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")


class WordAddIn(BaseModel):
    word: str = Field(..., min_length=1)
    clue: Optional[str] = None


class WordReplaceIn(BaseModel):
    old: str = Field(..., min_length=1)
    new: str = Field(..., min_length=1)
    clue: Optional[str] = None


class PuzzleRegenerateIn(BaseModel):
    add_words: Optional[list[WordAddIn]] = None
    remove_words: Optional[list[str]] = None
    replace_words: Optional[list[WordReplaceIn]] = None
    settings: Optional[EngineSettingsIn] = None
    clue_mode: Optional[str] = Field(None, pattern="^(automatic|manual|hybrid)$")
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    min_density: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_crossings: Optional[int] = Field(None, ge=0, le=100)
    auto_retry: bool = False
    max_retries: int = Field(3, ge=0, le=10)


class PuzzleExportIn(BaseModel):
    kind: str = Field("puzzle", pattern="^(puzzle|clues|answer_key|puzzle_with_clues)$")
    format: str = Field("svg", pattern="^(svg|pdf|png)$")
    page: int = Field(0, ge=0)
    force: bool = False
    title_override: Optional[str] = None
    solution_title_override: Optional[str] = None
    settings: ExportSettingsIn = ExportSettingsIn()


class ProjectSolutionPreviewIn(BaseModel):
    chapter_index: int = Field(0, ge=0)
    solutions_per_page: int = Field(4, ge=1, le=12)
    title_enabled: bool = True
    title_mode: str = Field("chapter_name", pattern="^(chapter_name|custom)$")
    title_template: str = ""
    title_start_number: int = Field(1, ge=1, le=999)
    settings: ExportSettingsIn = ExportSettingsIn()


class BulkGenerateIn(BaseModel):
    collection_ids: list[int] = Field(..., min_length=1)
    clue_mode: str = Field("hybrid", pattern="^(automatic|manual|hybrid)$")
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    generate_missing_clues: bool = True
    max_words_per_puzzle: Optional[int] = Field(None, ge=5, le=100)
    max_workers: int = Field(2, ge=1, le=8)
    min_density: float = Field(0.15, ge=0.0, le=1.0)
    min_crossings: Optional[int] = Field(None, ge=0, le=100)
    auto_retry: bool = True
    max_retries: int = Field(3, ge=0, le=10)
    settings: EngineSettingsIn = EngineSettingsIn()


class BulkZipExportIn(BaseModel):
    puzzle_ids: Optional[list[int]] = None
    job_id: Optional[str] = None
    kinds: list[str] = Field(default_factory=lambda: ["puzzle", "clues", "answer_key"])
    formats: list[str] = Field(default_factory=lambda: ["svg", "pdf"])
    force: bool = False
    settings: ExportSettingsIn = ExportSettingsIn()


class BulkBookPdfExportIn(BaseModel):
    puzzle_ids: Optional[list[int]] = None
    job_id: Optional[str] = None
    include_separate_clue_pages: bool = False
    force: bool = False
    settings: ExportSettingsIn = ExportSettingsIn()


class ProjectCreateIn(BaseModel):
    name: str = Field("Untitled Crossword Book", min_length=1, max_length=255)
    project_type: str = Field("crossword", min_length=1, max_length=64)
    trim_size: str = Field("6x9", min_length=1, max_length=64)
    current_step: int = Field(1, ge=1, le=4)
    settings: dict = Field(default_factory=dict)


class ProjectUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    project_type: Optional[str] = Field(None, min_length=1, max_length=64)
    trim_size: Optional[str] = Field(None, min_length=1, max_length=64)
    current_step: Optional[int] = Field(None, ge=1, le=4)
    settings: Optional[dict] = None
    import_metadata: Optional[dict] = None


class ProjectPasteImportIn(BaseModel):
    text: str = Field(..., min_length=1)
    collection_name: Optional[str] = None
    language: str = Field("en", min_length=2, max_length=16)
    first_line_is_title: Optional[bool] = None


class ProjectAcceptImportIn(BaseModel):
    replace_existing: bool = True


class ProjectRestoreJsonIn(BaseModel):
    schema_version: Optional[int] = 1
    name: str = Field(..., min_length=1, max_length=255)
    project_type: str = "crossword"
    trim_size: str = "6x9"
    current_step: int = Field(1, ge=1, le=4)
    settings: dict = Field(default_factory=dict)
    import_metadata: dict = Field(default_factory=dict)
    chapters: list[dict] = Field(default_factory=list)


class ChapterInlineActionIn(BaseModel):
    action: str = Field(
        ...,
        pattern="^(edit_word|remove_word|larger_grid|new_seed|auto_retry|reproduce)$",
    )
    old_word: Optional[str] = None
    new_word: Optional[str] = None
    clue: Optional[str] = None
    seed: Optional[int] = None
    rows: Optional[int] = Field(None, ge=3, le=60)
    cols: Optional[int] = Field(None, ge=3, le=60)
    max_size: Optional[int] = Field(None, ge=5, le=60)
    auto_retry: bool = False
