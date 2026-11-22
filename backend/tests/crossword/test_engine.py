import random
import string

import pytest

from app.crossword.engine import (
    EngineSettings, PlacedEntry, WordInput, generate_crossword, normalize_answer, preprocess_words, validate_grid,
)

VOCAB = (
    "apple elephant astronomy abundant courage planet river mountain ocean island forest desert valley "
    "bridge castle garden window pencil teacher student library science history music dance paint story "
    "poem rhythm melody harmony journey harvest compass lantern meadow thunder whisper horizon canyon"
).split()


def words(items):
    return preprocess_words(items).accepted


def fast(**kw):
    base = dict(attempts_per_size=3, polish_attempts=1, max_nodes_per_attempt=1500, time_limit_s=15)
    base.update(kw)
    return EngineSettings(**base)


def assert_accounted(result, supplied):
    placed = [e.answer for e in result.entries]
    unplaced = [u.answer for u in result.unplaced]
    assert sorted(placed + unplaced) == sorted(supplied)


# ---- preprocessing -------------------------------------------------------
def test_normalize():
    assert normalize_answer("Ice-cream") == ("ICECREAM", None)
    assert normalize_answer("café") == ("CAFE", None)
    assert normalize_answer("abc123")[0] is None
    assert normalize_answer("  ")[0] is None


def test_preprocess_reports_everything():
    r = preprocess_words(["apple", "APPLE", "", "x", "r2d2", "banana"], min_len=2)
    assert [w.answer for w in r.accepted] == ["APPLE", "BANANA"]
    assert len(r.duplicates) == 1
    assert len(r.rejected) == 3  # empty, too short, digits


# ---- generation ----------------------------------------------------------
def test_small_list_complete_and_valid():
    r = generate_crossword(words(["apple", "elephant", "astronomy", "courage", "planet"]), fast())
    assert r.status == "complete" and r.validation.valid
    assert not r.unplaced
    assert all(r.validation.checks.values())


def test_thirty_words_valid_and_accounted():
    supplied = [w.upper() for w in VOCAB[:30]]
    r = generate_crossword(words(supplied), fast())
    assert r.validation.valid
    assert_accounted(r, supplied)
    assert len(r.entries) >= 25  # nearly everything should fit; anything else must be reported


def test_no_common_letters_reports_unplaced():
    r = generate_crossword(words(["aaaa", "bbbb", "cccc"]), fast(max_size=10))
    assert r.status == "partial" and r.validation.valid
    assert len(r.entries) == 1 and len(r.unplaced) == 2
    assert all("no letters" in u.reason for u in r.unplaced)


def test_many_common_letters():
    supplied = ["LEVEL", "LEVER", "REVEL", "ELEVEN", "RELEVE", "EVERLEE"]
    r = generate_crossword(words(supplied), fast())
    assert r.validation.valid
    assert_accounted(r, supplied)


def test_long_words():
    supplied = ["EXTRAORDINARY", "INCOMPREHENSIBLE", "CONSTITUTION", "PHOTOSYNTHESIS", "ARCHAEOLOGY", "ELECTRICITY"]
    r = generate_crossword(words(supplied), fast())
    assert r.validation.valid
    assert_accounted(r, supplied)


def test_word_longer_than_max_is_reported_not_dropped():
    supplied = ["ABCDEFGHIJKLMNOP", "ABCD", "BCDE"]
    r = generate_crossword(words(supplied), fast(max_size=8))
    assert any(u.answer == "ABCDEFGHIJKLMNOP" and "longer" in u.reason for u in r.unplaced)
    assert_accounted(r, supplied)


def test_duplicate_input_words_are_reported():
    from app.crossword.engine import WordInput
    dup = [WordInput("APPLE"), WordInput("APPLE"), WordInput("PLANET")]
    r = generate_crossword(dup, fast())
    assert any("duplicate" in u.reason for u in r.unplaced)
    assert_accounted(r, ["APPLE", "APPLE", "PLANET"])


def test_deterministic_for_same_seed():
    ws = words(VOCAB[:15])
    a = generate_crossword(ws, fast(seed=7, time_limit_s=60))
    b = generate_crossword(ws, fast(seed=7, time_limit_s=60))
    assert a.cells == b.cells


def test_custom_dimensions_respected():
    r = generate_crossword(words(VOCAB[:8]), fast(rows=15, cols=15))
    assert (r.rows, r.cols) == (15, 15)
    assert len(r.cells) == 15 and all(len(row) == 15 for row in r.cells)
    assert r.validation.valid


def test_custom_dimensions_too_small_reports_unplaced():
    supplied = [w.upper() for w in VOCAB[:20]]
    r = generate_crossword(words(supplied), fast(rows=6, cols=6))
    assert r.validation.valid and r.unplaced
    assert_accounted(r, supplied)


def test_numbering_is_row_major():
    r = generate_crossword(words(["apple", "elephant", "planet"]), fast())
    starts = sorted({(e.row, e.col) for e in r.entries})
    for e in r.entries:
        assert e.number == starts.index((e.row, e.col)) + 1


def test_symmetry_option_never_breaks_validity():
    r = generate_crossword(words(VOCAB[:12]), fast(symmetry="preferred"))
    assert r.validation.valid
    assert 0 <= r.stats["symmetry_ratio"] <= 1


def test_fuzz_random_lists_always_valid():
    rng = random.Random(1)
    for _ in range(25):
        supplied = ["".join(rng.choice("AEIOURSTLN") for _ in range(rng.randint(3, 8))) for _ in range(rng.randint(2, 14))]
        r = generate_crossword(words(supplied), fast(attempts_per_size=2, max_nodes_per_attempt=400, time_limit_s=5))
        assert r.validation.valid, (supplied, r.validation.errors)
        assert_accounted(r, [w.answer for w in words(supplied)] + [d["answer"] for d in preprocess_words(supplied).duplicates])


# ---- validator catches broken grids -------------------------------------
def grid_from(rows):
    return [[ch if ch != "." else None for ch in row] for row in rows]


def entry(answer, r, c, d, n=None):
    return PlacedEntry(answer, r, c, d, None, n)


def test_validator_flags_accidental_word():
    cells = grid_from(["CAT", "AB.", "T.."])
    entries = [entry("CAT", 0, 0, "A", 1), entry("CAT", 0, 0, "D", 1)]
    rep = validate_grid(cells, entries)
    assert not rep.valid and not rep.checks["no_accidental_words"]


def test_validator_flags_disconnected():
    cells = grid_from(["CAT....", ".......", "....DOG"])
    entries = [entry("CAT", 0, 0, "A", 1), entry("DOG", 2, 4, "A", 2)]
    rep = validate_grid(cells, entries)
    assert not rep.valid and not rep.checks["connected"]


def test_validator_flags_letter_mismatch():
    cells = grid_from(["CAT"])
    rep = validate_grid(cells, [entry("COT", 0, 0, "A", 1)])
    assert not rep.valid and not rep.checks["entry_letters_match"]


def test_validator_flags_bad_numbering_and_missing_words():
    cells = grid_from(["CAT"])
    assert not validate_grid(cells, [entry("CAT", 0, 0, "A", 5)]).checks["numbering"]
    rep = validate_grid(cells, [entry("CAT", 0, 0, "A", 1)], expected=["CAT", "DOG"], unplaced=[])
    assert not rep.checks["every_word_accounted_for"]


def test_validator_accepts_good_grid():
    cells = grid_from(["CAT", "A..", "R.."])
    entries = [entry("CAT", 0, 0, "A", 1), entry("CAR", 0, 0, "D", 1)]
    assert validate_grid(cells, entries).valid


def test_default_min_word_length_is_3():
    assert EngineSettings().min_word_length == 3
    r = preprocess_words(["ab", "cat", "dog"])
    assert [w.answer for w in r.accepted] == ["CAT", "DOG"]
    assert len(r.rejected) == 1
    assert "shorter than the minimum length of 3" in r.rejected[0]["reason"]

    res = generate_crossword([WordInput("AB"), WordInput("CAT"), WordInput("CAR")])
    assert any(u.answer == "AB" and "minimum length of 3" in u.reason for u in res.unplaced)

    r_two = preprocess_words(["ab", "cat"], min_len=2)
    assert [w.answer for w in r_two.accepted] == ["AB", "CAT"]
    res_two = generate_crossword(
        [WordInput("AB"), WordInput("CAT"), WordInput("BAT")],
        EngineSettings(min_word_length=2),
    )
    assert res_two.validation.valid


def test_format_enumeration():
    from app.crossword.engine import format_enumeration

    assert format_enumeration("ICECREAM", "ice cream") == "(3,5)"
    assert format_enumeration("ICECREAM", "ice-cream") == "(3-5)"
    assert format_enumeration("FOURLEAF", "four-leaf") == "(4-4)"
    assert format_enumeration("MOTHERINLAW", "mother-in-law") == "(6-2-3)"
    assert format_enumeration("NEWYORKBASED", "New York-based") == "(3,4-5)"
    assert format_enumeration("DONT", "don't") == "(4)"
    assert format_enumeration("APPLE", "apple") == "(5)"
    assert format_enumeration("ICECREAM", "ice cream", style="total") == "(8)"
    assert format_enumeration("ICECREAM", "ice cream", style="none") == ""
    assert format_enumeration("ICECREAM", "ice cream", style=False) == ""

