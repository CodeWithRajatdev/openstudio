import pytest

from app.wordsearch.engine import (Difficulty, GenerationError, PuzzleConfig, SizingMode,
                        difficulty_preset, generate_puzzle, validate_puzzle)
from app.wordsearch.engine.directions import DIRECTIONS, allowed_directions
from app.wordsearch.engine.generator import (
    ENGLISH_LETTER_FREQUENCIES,
    INAPPROPRIATE_WORDS,
    _candidates,
    _validate_and_refill_grid,
    _weighted_fill_distribution,
)
from app.wordsearch.engine.models import Placement
from app.wordsearch.engine.normalize import InvalidWordError, normalize_word

WORDS = ["APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON"]


def read_path(puzzle, p):
    return "".join(puzzle.grid[r][c] for r, c in p.cells())


# ---- all eight directions ---------------------------------------------------
@pytest.mark.parametrize("d", list(DIRECTIONS))
def test_each_direction_places_and_reads_correctly(d):
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=8, cols=8,
                       directions=[d], seed=1)
    puz = generate_puzzle(["TIGER", "LION"], cfg)
    assert {p.direction for p in puz.placements} == {d}
    for p in puz.placements:
        assert read_path(puz, p) == p.grid_word
    assert validate_puzzle(puz, ["TIGER", "LION"]) == []


# ---- reverse ---------------------------------------------------------------
def test_reverse_flag_controls_reverse_directions():
    assert set(allowed_directions(True, True, True, False)) == {"E", "S", "SE", "SW"}
    assert len(allowed_directions(True, True, True, True)) == 8
    assert allowed_directions(True, False, False, True) == ["E", "W"]


def test_reverse_word_keeps_clue_spelling():
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=7, cols=7,
                       directions=["W"], seed=3)
    puz = generate_puzzle(["APPLE"], cfg)
    p = puz.placements[0]
    assert p.original == "APPLE" and p.grid_word == "APPLE"
    row = "".join(puz.grid[p.start_row])
    assert p.direction == "W"
    # Reading the grid left-to-right shows the word reversed.
    assert "ELPPA" in row


# ---- overlaps and conflicts -----------------------------------------------
def test_matching_overlap_allowed_and_conflict_rejected():
    grid = [[None] * 5 for _ in range(5)]
    grid[0][0], grid[0][1] = "A", "B"
    cands = _candidates(grid, 5, 5, "ABC", ["E"])
    assert (0, 0, "E") in cands            # A,B match; C fills empty cell
    assert (0, 1, "E") not in cands        # B vs A conflict at (0,1)


def test_overlap_makes_tight_grid_possible():
    # 3x3 holds CAT, COT, CUT only if they share letters in a valid way.
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=3, cols=3, seed=5,
                       attempts_per_size=200)
    puz = generate_puzzle(["CAT", "COT"], cfg)
    assert validate_puzzle(puz, ["CAT", "COT"]) == []


# ---- boundaries and sizing -----------------------------------------------
def test_boundary_word_longer_than_grid_has_no_candidates():
    grid = [[None] * 4 for _ in range(4)]
    assert _candidates(grid, 4, 4, "ELEPHANT", list(DIRECTIONS)) == []


def test_manual_mode_fails_loudly():
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=5, cols=5, seed=1)
    with pytest.raises(GenerationError) as e:
        generate_puzzle(["EXTRAORDINARILY", "CAT"], cfg)
    assert "EXTRAORDINARILY" in e.value.failed_words
    assert e.value.suggestions


def test_manual_auto_adjust_expands():
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL_AUTO_ADJUST, rows=12, cols=12,
                       seed=2)
    words = ["EXTRAORDINARILYLONG", "CAT", "DOG"]
    puz = generate_puzzle(words, cfg)
    assert puz.rows >= 19 and puz.cols >= 19
    assert puz.sizes_tried[0] == (12, 12) and puz.sizes_tried[-1] == (puz.rows, puz.cols)
    assert validate_puzzle(puz, words) == []


def test_auto_adjust_stops_at_max_and_reports():
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL_AUTO_ADJUST, rows=4, cols=4,
                       max_rows=6, max_cols=6, seed=1)
    with pytest.raises(GenerationError) as e:
        generate_puzzle(["ABCDEFGHIJ"], cfg)
    assert e.value.sizes_tried[-1] == (6, 6)


def test_auto_mode_places_everything():
    puz = generate_puzzle(WORDS, PuzzleConfig(seed=9))
    assert sorted(p.original for p in puz.placements) == sorted(WORDS)
    assert puz.rows == puz.cols >= 6


# ---- normalisation -----------------------------------------------------------
def test_multiword_normalisation_keeps_display_phrase():
    assert normalize_word("Ice Cream") == "ICECREAM"
    assert normalize_word("don't") == "DONT"
    assert normalize_word("Café") == "CAFE"
    puz = generate_puzzle(["ice cream", "tiger"], PuzzleConfig(seed=4))
    p = next(p for p in puz.placements if p.original == "ice cream")
    assert p.grid_word == "ICECREAM"


def test_invalid_words_are_reported_not_dropped():
    with pytest.raises(InvalidWordError):
        normalize_word("12 !!")
    with pytest.raises(GenerationError) as e:
        generate_puzzle(["CAT", "???"], PuzzleConfig(seed=1))
    assert e.value.failed_words == ["???"]


def test_duplicates_after_normalisation_rejected():
    with pytest.raises(GenerationError):
        generate_puzzle(["Ice Cream", "icecream"], PuzzleConfig(seed=1))


def test_no_words_or_no_directions():
    with pytest.raises(GenerationError):
        generate_puzzle([])
    with pytest.raises(GenerationError):
        generate_puzzle(["CAT"], PuzzleConfig(horizontal=False, vertical=False,
                                              diagonal=False))


# ---- difficulty ---------------------------------------------------------------
def test_difficulty_presets_and_overrides():
    e = difficulty_preset(Difficulty.EASY)
    assert (e.horizontal, e.vertical, e.diagonal, e.reverse) == (True, False, False, False)
    h = difficulty_preset(Difficulty.HARD)
    assert h.reverse and h.diagonal
    m = difficulty_preset(Difficulty.MEDIUM, reverse=True)
    assert m.reverse
    puz = generate_puzzle(WORDS, difficulty_preset(Difficulty.EASY, seed=1))
    assert {p.direction for p in puz.placements} == {"E"}


# ---- answer-key metadata accuracy ----------------------------------------------
def test_placement_metadata_matches_grid_for_hard_puzzle():
    cfg = difficulty_preset(Difficulty.HARD, seed=11)
    puz = generate_puzzle(WORDS * 1 + ["PINEAPPLE", "WATERMELON"], cfg)
    for p in puz.placements:
        assert read_path(puz, p) == p.grid_word
        cells = p.cells()
        assert cells[0] == (p.start_row, p.start_col)
        assert cells[-1] == (p.end_row, p.end_col)
        assert p.puzzle_id == puz.puzzle_id


def test_validator_catches_tampering():
    puz = generate_puzzle(WORDS, PuzzleConfig(seed=2))
    p = puz.placements[0]
    r, c = p.start_row, p.start_col
    puz.grid[r][c] = "#" if puz.grid[r][c] != "#" else "@"
    assert validate_puzzle(puz, WORDS)


# ---- reproducibility ------------------------------------------------------------
def test_same_seed_same_puzzle_different_seed_differs():
    a = generate_puzzle(WORDS, PuzzleConfig(seed=42), puzzle_id="x")
    b = generate_puzzle(WORDS, PuzzleConfig(seed=42), puzzle_id="x")
    c = generate_puzzle(WORDS, PuzzleConfig(seed=43), puzzle_id="x")
    assert a.grid == b.grid and a.placements == b.placements
    assert a.grid != c.grid


def test_unseeded_generation_records_seed_and_is_reproducible():
    a = generate_puzzle(WORDS, PuzzleConfig(), puzzle_id="y")
    b = generate_puzzle(WORDS, PuzzleConfig(seed=a.seed), puzzle_id="y")
    assert a.grid == b.grid


# ---- scale -------------------------------------------------------------------------
def test_bulk_100_chapters_all_validate():
    import random
    rng = random.Random(0)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i in range(100):
        words = set()
        while len(words) < 20:
            words.add("".join(rng.choice(letters) for _ in range(rng.randint(4, 12))))
        words = sorted(words)
        puz = generate_puzzle(words, difficulty_preset(Difficulty.HARD, seed=i))
        assert validate_puzzle(puz, words) == []


def test_backtracking_csp_solves_tight_constrained_grid_in_single_attempt():
    # A 3x3 grid with 6 interlocking 3-letter words requires stepping back when
    # early words choose coordinates that block later words.
    words = ["CAT", "ARE", "RED", "CAR", "TED", "ERA"]
    cfg = PuzzleConfig(
        sizing_mode=SizingMode.MANUAL,
        rows=3,
        cols=3,
        reverse=True,
        attempts_per_size=1,
        seed=7,
    )
    puz = generate_puzzle(words, cfg)
    assert validate_puzzle(puz, words) == []


def test_weighted_english_letter_frequency_filler():
    assert ENGLISH_LETTER_FREQUENCIES["E"] > 10.0
    assert ENGLISH_LETTER_FREQUENCIES["Z"] < 0.2
    cfg = PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=25, cols=25, seed=123)
    puz = generate_puzzle(["APPLE"], cfg)
    placed_cells = set(puz.placements[0].cells())
    filler = [
        puz.grid[r][c]
        for r in range(puz.rows)
        for c in range(puz.cols)
        if (r, c) not in placed_cells
    ]
    common_count = sum(1 for ch in filler if ch in {"E", "T", "A", "O", "I", "N"})
    rare_count = sum(1 for ch in filler if ch in {"Z", "Q", "X", "J"})
    assert common_count > len(filler) * 0.35
    assert rare_count < len(filler) * 0.05


def test_bulk_365_dense_chapters_performance():
    import random
    import time
    rng = random.Random(42)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    t0 = time.perf_counter()
    for i in range(365):
        words = set()
        while len(words) < 20:
            words.add("".join(rng.choice(letters) for _ in range(rng.randint(5, 11))))
        puz = generate_puzzle(sorted(words), difficulty_preset(Difficulty.HARD, seed=i))
        assert len(puz.placements) == 20
    elapsed = time.perf_counter() - t0
    assert elapsed < 15.0


def test_post_fill_validation_removes_accidental_duplicates_and_inappropriate_words():
    import random

    # Construct a 6x6 grid with one intentional placement: CAT horizontally at row 0, cols 0..2
    grid = [
        ["C", "A", "T", "Q", "Q", "Q"],
        ["Q", "C", "Q", "Q", "Q", "T"],  # diagonal SE accidental CAT at (1,1)->(3,3)
        ["Q", "Q", "A", "Q", "Q", "A"],  # vertical N (reverse) accidental CAT at (3,5)->(1,5)
        ["Q", "Q", "Q", "T", "Q", "C"],
        ["F", "U", "C", "K", "Q", "Q"],  # horizontal inappropriate word at row 4, cols 0..3
        ["Q", "Q", "Q", "Q", "Q", "Q"],
    ]
    placement = Placement(
        puzzle_id="p",
        original="CAT",
        grid_word="CAT",
        start_row=0,
        start_col=0,
        end_row=0,
        end_col=2,
        direction="E",
    )
    fill_letters, fill_cum_weights = _weighted_fill_distribution("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    rng = random.Random(99)

    refilled = _validate_and_refill_grid(
        grid, [placement], rng, fill_letters, fill_cum_weights
    )
    assert refilled > 0
    # Intentional placement remains untouched
    assert "".join(grid[0][:3]) == "CAT"
    # Accidental diagonal & vertical duplicates and inappropriate word were broken
    assert (grid[1][1], grid[2][2], grid[3][3]) != ("C", "A", "T")
    assert (grid[3][5], grid[2][5], grid[1][5]) != ("C", "A", "T")
    assert "".join(grid[4][:4]) != "FUCK"
    # Unrelated cells untouched by localized refill
    assert grid[0][3] == "Q"
    assert grid[5][5] == "Q"


def test_generated_puzzles_contain_no_accidental_duplicates_or_inappropriate_strings():
    # Generate dense small-word puzzles and verify across all 8 directions that
    # neither accidental duplicate clues nor inappropriate words survive in the grid.
    words = ["CAT", "DOG", "BAT", "RAT", "SUN", "MOM"]
    for seed in range(25):
        puz = generate_puzzle(
            words,
            PuzzleConfig(sizing_mode=SizingMode.MANUAL, rows=10, cols=10, reverse=True, seed=seed),
        )
        assert validate_puzzle(puz, words) == []
        locked = {cell for p in puz.placements for cell in p.cells()}
        intended = {
            p.grid_word: {tuple(p.cells()), tuple(reversed(p.cells()))}
            for p in puz.placements
        }
        for r in range(puz.rows):
            for c in range(puz.cols):
                for d, (dr, dc) in DIRECTIONS.items():
                    for target in list(intended.keys()) + list(INAPPROPRIATE_WORDS):
                        n = len(target)
                        er, ec = r + (n - 1) * dr, c + (n - 1) * dc
                        if not (0 <= er < puz.rows and 0 <= ec < puz.cols):
                            continue
                        span = tuple((r + i * dr, c + i * dc) for i in range(n))
                        text = "".join(puz.grid[rr][cc] for rr, cc in span)
                        if text == target and any(cell not in locked for cell in span):
                            assert target in intended and span in intended[target], (
                                f"Seed {seed}: unexpected {target!r} at {span} ({d})"
                            )


def test_reverse_placement_ratio_is_20_to_30_percent():
    from app.wordsearch.engine.directions import REVERSE
    words_16 = [
        "APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON", "CHERRY", "PEACH",
        "MELON", "KIWI", "PLUM", "PAPAYA", "GUAVA", "APRICOT", "BERRY", "FIG",
    ]
    rev_set = set(REVERSE)
    counts = []
    for seed in range(20):
        puz = generate_puzzle(words_16, difficulty_preset(Difficulty.HARD, seed=seed))
        rev_count = sum(1 for p in puz.placements if p.direction in rev_set)
        counts.append(rev_count)
        assert 3 <= rev_count <= 5, f"Seed {seed}: expected 3-5 reverse words, got {rev_count}"
    avg_ratio = sum(counts) / (len(counts) * len(words_16))
    assert 0.20 <= avg_ratio <= 0.30


