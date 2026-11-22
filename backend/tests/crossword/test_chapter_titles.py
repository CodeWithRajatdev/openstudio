"""First-line chapter titles: the first non-blank line of each chapter block is its title."""
from __future__ import annotations

from app.crossword.services.export.geometry import ExportEntry, ExportPuzzleData, build_solution_pages
from app.crossword.services.export.primitives import TextPrimitive
from app.crossword.services.export.settings import ExportSettings
from app.crossword.services.importer import parse_import_payload

USER_EXAMPLE = """1. Sense of Organs
Nose| Helps breathe
Ear | Helps hear
Eye | Helps see

2. Farm animals
Cow | a farm animal that gives milk
Hen | a farm bird that lays eggs
Pig | a pink farm animal
"""


def _parse(text: str, *, first_line_is_title: bool, filename: str = "words.txt"):
    _, report, staged = parse_import_payload(
        text=text,
        filename=filename,
        first_line_is_title=first_line_is_title,
        run_trial_placement=False,
        group_prefix="Chapter",
    )
    return report, staged


def test_titles_on_txt_uses_first_line_as_chapter_name_and_strips_numbering():
    report, staged = _parse(USER_EXAMPLE, first_line_is_title=True)
    names = [g["name"] for g in report["chapters"]]
    assert names == ["Sense of Organs", "Farm animals"]

    organs = report["chapters"][0]
    assert [w["answer"] for w in organs["words"]] == ["NOSE", "EAR", "EYE"]
    assert organs["words"][0]["clue"] == "Helps breathe"
    assert report["invalid_count"] == 0

    # Titles are reported, with the raw line kept, never silently consumed
    titles = report["chapter_titles"]
    assert [t["title"] for t in titles] == ["Sense of Organs", "Farm animals"]
    assert titles[0]["raw"] == "1. Sense of Organs"
    assert titles[0]["row"] == 1
    assert titles[1]["row"] == 6
    assert [g["name"] for g in staged["groups"]] == ["Sense of Organs", "Farm animals"]


def test_titles_off_keeps_existing_behaviour():
    report, _ = _parse(USER_EXAMPLE, first_line_is_title=False)
    assert [g["name"] for g in report["chapters"]] == ["Chapter 1", "Chapter 2"]
    # The title lines are reported as invalid words (not silently dropped)
    assert report["invalid_count"] == 2
    assert report.get("chapter_titles", []) == []


def test_titles_on_csv_with_header_after_title():
    text = "Body Parts,\nword,clue\nnose,helps breathe\near,helps hear\n\nPets,\nword,clue\ncat,meows\ndog,barks\n"
    report, _ = _parse(text, first_line_is_title=True, filename="words.csv")
    assert [g["name"] for g in report["chapters"]] == ["Body Parts", "Pets"]
    assert [w["answer"] for w in report["chapters"][1]["words"]] == ["CAT", "DOG"]
    assert report["invalid_count"] == 0


def test_titles_on_single_block_without_blank_lines():
    text = "Weather\nrain|falls from clouds\nsnow|cold white flakes\n"
    report, _ = _parse(text, first_line_is_title=True)
    assert [g["name"] for g in report["chapters"]] == ["Weather"]
    assert len(report["chapters"][0]["words"]) == 2


def test_duplicate_titles_never_merge_chapters_and_are_reported():
    text = "Animals\ncat|meows\ndog|barks\n\nAnimals\ncow|moos\nhen|clucks\n"
    report, _ = _parse(text, first_line_is_title=True)
    names = [g["name"] for g in report["chapters"]]
    assert names == ["Animals", "Animals (2)"]
    assert [w["answer"] for w in report["chapters"][1]["words"]] == ["COW", "HEN"]
    assert any(w.get("type") == "duplicate_chapter_title" for w in report["warnings"])


def test_title_without_words_is_reported():
    text = "Empty Chapter\n\nFruits\napple|red fruit\npear|green fruit\n"
    report, _ = _parse(text, first_line_is_title=True)
    assert [g["name"] for g in report["chapters"]] == ["Fruits"]
    assert any(
        w.get("type") == "chapter_title_without_words" and "Empty Chapter" in w["reason"]
        for w in report["warnings"]
    )


def test_title_line_with_clue_data_is_warned():
    # User turned titles on but the file has no title lines: first word becomes title, with a warning
    text = "nose|helps breathe\near|helps hear\neye|helps see\n"
    report, _ = _parse(text, first_line_is_title=True)
    assert report["chapters"][0]["name"] == "nose"
    assert any(w.get("type") == "title_line_extra_data" for w in report["warnings"])


def test_chapter_title_appears_on_answer_pages():
    puz = ExportPuzzleData(
        title="Sense of Organs",
        rows=3,
        cols=3,
        grid=["EYE", "A#A", "R#R"],
        entries=[
            ExportEntry(number=1, direction="A", row=0, col=0, answer="EYE", clue="Helps see", display="eye"),
            ExportEntry(number=1, direction="D", row=0, col=0, answer="EAR", clue="Helps hear", display="ear"),
        ],
    )
    pages = build_solution_pages([puz], ExportSettings(page_size="6x9", font_family="Open Sans"))
    texts = [p.text for p in pages[0].primitives if isinstance(p, TextPrimitive)]
    assert "Sense of Organs" in texts


def test_puzzle_and_solution_title_modes_custom_vs_chapter_name():
    from app.crossword.services.export.geometry import build_export_pages
    from app.crossword.services.projects import resolve_chapter_display_title

    # Mode = "chapter_name": uses the chapter name from the TXT/CSV file directly
    assert (
        resolve_chapter_display_title(
            chapter_name="Sense of Organs",
            puzzle_number=1,
            mode="chapter_name",
            template="Custom #{PUZZLE_NUMBER}",
            enabled=True,
        )
        == "Sense of Organs"
    )

    # Mode = "custom": formats template with {PUZZLE_NUMBER} and {CHAPTER_TITLE}
    assert (
        resolve_chapter_display_title(
            chapter_name="Sense of Organs",
            puzzle_number=1,
            mode="custom",
            template="Puzzle #{PUZZLE_NUMBER} - {CHAPTER_TITLE}",
            enabled=True,
        )
        == "Puzzle #1 - Sense of Organs"
    )

    # ExportPuzzleData supports independent title (puzzle page) and solution_title (solution page)
    puz = ExportPuzzleData(
        title="Puzzle #1 - Sense of Organs",
        solution_title="Answer 1: Sense of Organs",
        rows=3,
        cols=3,
        grid=["EYE", "A#A", "R#R"],
        entries=[
            ExportEntry(number=1, direction="A", row=0, col=0, answer="EYE", clue="Helps see", display="eye"),
            ExportEntry(number=1, direction="D", row=0, col=0, answer="EAR", clue="Helps hear", display="ear"),
        ],
    )
    settings = ExportSettings(page_size="6x9", font_family="Open Sans")
    puz_pages = build_export_pages(puz, "puzzle_with_clues", settings)
    puz_texts = [p.text for p in puz_pages[0].primitives if isinstance(p, TextPrimitive)]
    assert "Puzzle #1 - Sense of Organs" in puz_texts

    sol_pages = build_solution_pages([puz], settings)
    sol_texts = [p.text for p in sol_pages[0].primitives if isinstance(p, TextPrimitive)]
    assert "Answer 1: Sense of Organs" in sol_texts

