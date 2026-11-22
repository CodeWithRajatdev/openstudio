import io

import pytest
from openpyxl import Workbook

from app.wordsearch.engine import PuzzleConfig
from app.wordsearch.engine.bulk import generate_chapters
from app.wordsearch.engine.normalize import NormalizeRules
from app.wordsearch.importers import (ImportError_, ImportOptions, ImportValidationError, WordBank,
                           import_file)
from app.wordsearch.importers.parsers import parse_blocks  # noqa: F401


def codes(res):
    return [i.code for i in res.issues]


def xlsx_bytes(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ CSV
def test_csv_long_format_groups_chapters_in_order():
    data = b"Chapter,Word\nFruits,apple\nAnimals,tiger\nFruits,mango\nAnimals,lion\n"
    res = import_file("w.csv", data)
    assert res.layout == "long" and res.ready
    assert [(c.title, [w.text for w in c.words]) for c in res.bank.chapters] == [
        ("Fruits", ["apple", "mango"]), ("Animals", ["tiger", "lion"])]
    assert res.bank.chapters[0].words[1].source == "row 4, col 2"


def test_csv_wide_format_uses_headers_as_titles_and_reports_interior_blanks():
    data = b"Fruits,Animals\napple,tiger\n,lion\nmango,\n"
    res = import_file("w.csv", data, ImportOptions(layout="wide"))
    assert res.layout == "wide"
    assert [w.text for w in res.bank.chapters[0].words] == ["apple", "mango"]
    assert [w.text for w in res.bank.chapters[1].words] == ["tiger", "lion"]
    auto = import_file("w.csv", data)            # auto reads column A only and says so
    assert auto.layout == "blocks" and "extra_columns_ignored" in codes(auto)
    blanks = [i for i in res.issues if i.code == "blank_entry"]
    assert len(blanks) == 1 and blanks[0].chapter == "Fruits"   # interior only


def test_csv_single_column_and_semicolon_delimiter_and_bom():
    res = import_file("w.csv", b"\xef\xbb\xbfapple\nmango\nkiwi\n")
    assert res.layout == "blocks" and res.bank.stats() == {"chapters": 1, "words": 3}
    assert res.bank.chapters[0].title == "Chapter 1"
    res = import_file("w.csv", b"Chapter;Word\nA;one\nA;two\n")
    assert res.layout == "long" and res.bank.stats()["words"] == 2


def test_csv_long_missing_chapter_is_flagged_not_dropped():
    res = import_file("w.csv", b"Chapter,Word\nFruits,apple\n,orphan\n")
    assert "missing_chapter" in codes(res)
    assert "orphan" in [w.text for c in res.bank.chapters for w in c.words]


def test_cp1252_fallback_warns():
    res = import_file("w.csv", "Word\ncaf\u00e9\n".encode("cp1252"))
    assert "encoding_fallback" in codes(res)
    assert res.bank.chapters[0].words[0].text == "caf\u00e9"


# ------------------------------------------------------------------ TXT
def test_txt_headings_styles():
    txt = ("Chapter 1: Fruits\napple\nmango\n\n# Animals\ntiger\nlion\n\n[Colours]\nred, blue\n"
           "Planets:\nmars\n")
    res = import_file("w.txt", txt.encode())
    got = {c.title: [w.text for w in c.words] for c in res.bank.chapters}
    assert got == {"Chapter 1: Fruits": ["apple", "mango"], "Animals": ["tiger", "lion"],
                   "Colours": ["red", "blue"], "Planets": ["mars"]}


def test_txt_blank_line_blocks_become_chapters():
    res = import_file("w.txt", b"apple\nmango\n\ntiger\nlion\n\nred\n")
    assert [c.title for c in res.bank.chapters] == ["Chapter 1", "Chapter 2", "Chapter 3"]


def test_txt_plain_list_is_one_chapter_and_multiword_phrase_kept():
    res = import_file("w.txt", b"ice cream\nsun\n")
    assert res.bank.stats() == {"chapters": 1, "words": 2}
    assert res.bank.chapters[0].words[0].text == "ice cream"


def test_txt_line_numbers_recorded():
    res = import_file("w.txt", b"# A\none\n\ntwo\n")
    assert [w.source for w in res.bank.chapters[0].words] == ["line 2", "line 4"]


# ----------------------------------------------------------------- XLSX
def test_xlsx_each_sheet_is_a_chapter_and_numbers_become_text():
    data = xlsx_bytes({"Fruits": [["apple"], ["mango"]], "Years": [[2024], [1999.0]]})
    res = import_file("w.xlsx", data)                       # all sheets, in order
    assert [c.title for c in res.bank.chapters] == ["Chapter 1", "Chapter 2"]
    assert [w.source for w in res.bank.chapters[0].words] == ["Fruits!A1", "Fruits!A2"]
    assert [w.text for w in res.bank.chapters[1].words] == ["2024", "1999"]
    assert [s["name"] for s in res.sheets] == ["Fruits", "Years"]
    assert [i.code for i in res.blocking] == ["invalid_word", "invalid_word"]


def test_xlsx_long_and_wide_layouts():
    long_ = xlsx_bytes({"A": [["Chapter", "Word"], ["C1", "one"], ["C1", "two"], ["C2", "three"]]})
    res = import_file("w.xlsx", long_)
    got = {c.title: [w.text for w in c.words] for c in res.bank.chapters}
    assert got == {"C1": ["one", "two"], "C2": ["three"]}
    assert res.bank.chapters[0].words[0].source == "A!B2"
    wide = xlsx_bytes({"B": [["Left", "Right"], ["a", "b"], ["c", None]]})
    res = import_file("w.xlsx", wide, ImportOptions(layout="wide"))
    got = {c.title: [w.text for w in c.words] for c in res.bank.chapters}
    assert got == {"Left": ["a", "c"], "Right": ["b"]}


# ------------------------------------------------------------ validation
def test_invalid_blank_duplicate_reported_never_dropped():
    data = b"Chapter,Word\nA,apple\nA,Apple\nA,12!\nA,ice cream\nA,icecream\n"
    res = import_file("w.csv", data)
    assert res.bank.stats()["words"] == 5            # nothing discarded
    assert codes(res).count("duplicate_in_chapter") == 2
    assert codes(res).count("invalid_word") == 1
    assert not res.ready


def test_cross_chapter_duplicates_optional():
    data = b"Chapter,Word\nA,apple\nB,APPLE\n"
    assert "duplicate_across_chapters" not in codes(import_file("w.csv", data))
    res = import_file("w.csv", data, check_cross_chapter=True)
    dup = [i for i in res.issues if i.code == "duplicate_across_chapters"]
    assert len(dup) == 1 and dup[0].severity == "warning" and res.ready


def test_word_too_long_and_rules_respected():
    data = b"Word\nextraordinarily\nice-cream\n"
    res = import_file("w.csv", data, max_word_length=10)
    assert [c for c in codes(res) if c != "header_row_skipped"] == ["word_too_long"]
    strict = NormalizeRules(remove_hyphens=False)
    assert "invalid_word" in codes(import_file("w.csv", data, rules=strict))


def test_original_input_preserved():
    data = b"Chapter,Word\nA,  apple  \n"
    res = import_file("w.csv", data)
    w = res.bank.chapters[0].words[0]
    assert w.raw == "  apple  " and w.text == "apple" and not w.edited
    assert res.original_bytes == data and len(res.sha256) == 64


@pytest.mark.parametrize("name,data,msg", [
    ("w.pdf", b"x", "Unsupported"), ("w.csv", b"   \n", "empty"),
    ("w.xlsx", b"not a zip", "Could not read"), ("w.csv", b"Chapter,Word\n", "No words")])
def test_unreadable_files_raise_clear_errors(name, data, msg):
    with pytest.raises(ImportError_, match=msg):
        import_file(name, data)


def test_file_size_limit():
    with pytest.raises(ImportError_, match="limit"):
        import_file("w.txt", b"a" * 50, ImportOptions(max_bytes=10))


# ---------------------------------------------------------------- editing
def test_edit_delete_add_remove_rename_flow_then_generate():
    res = import_file("w.csv", b"Chapter,Word\nA,apple\nA,Apple\nA,12!\nB,tiger\n")
    bank = res.bank
    with pytest.raises(ImportValidationError) as e:
        bank.to_chapters()
    assert len(e.value.issues) == 2
    bad = next(i for i in e.value.issues if i.code == "invalid_word")
    bank.edit_word(bad.word_id, "twelve")
    assert bank.find_word(bad.word_id)[1].edited
    removed = bank.remove_duplicates()
    assert [(t, w.text) for t, w in removed] == [("A", "Apple")]
    bank.add_word("B", "lion")
    bank.add_chapter("C", ["red", "blue"])
    bank.rename_chapter("C", "Colours")
    bank.remove_chapter("A")
    assert bank.to_chapters() == [("B", ["tiger", "lion"]), ("Colours", ["red", "blue"])]
    out = generate_chapters(bank.to_chapters(), PuzzleConfig(), base_seed=1)
    assert len(out.succeeded) == 2


def test_delete_word_and_missing_ids():
    bank = WordBank()
    bank.add_chapter("A", ["x1y"])
    with pytest.raises(KeyError):
        bank.find_word(999)
    with pytest.raises(KeyError):
        bank.remove_chapter("nope")
    w = bank.delete_word(1)
    assert w.raw == "x1y" and bank.stats()["words"] == 0


# ------------------------------------------------------------------ scale
def test_import_365_chapters_x_20_words_all_formats():
    import random
    rng = random.Random(3)
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    rows = []
    for c in range(365):
        ws = set()
        while len(ws) < 20:
            ws.add("".join(rng.choice(L) for _ in range(rng.randint(4, 12))))
        rows += [(f"Chapter {c + 1}", w) for w in sorted(ws)]
    csv_data = ("Chapter,Word\n" + "\n".join(f"{a},{b}" for a, b in rows)).encode()
    txt_data = "\n".join(
        (f"Chapter {c + 1}\n" + "\n".join(w for t, w in rows if t == f"Chapter {c + 1}"))
        for c in range(365)).encode()
    x_data = xlsx_bytes({"Words": [["Chapter", "Word"]] + [list(r) for r in rows]})
    for name, data in (("a.csv", csv_data), ("a.txt", txt_data), ("a.xlsx", x_data)):
        res = import_file(name, data)
        assert res.bank.stats() == {"chapters": 365, "words": 7300}, name
        assert res.ready, name
        assert len(res.bank.to_chapters()) == 365


def test_plain_words_that_look_like_keywords_are_not_headings():
    res = import_file("w.txt", b"# Misc\nBook\nLevel\nDay\nPart\nUnit\nWeek 2\nunity\n")
    got = {c.title: [w.text for w in c.words] for c in res.bank.chapters}
    assert got == {"Misc": ["Book", "Level", "Day", "Part", "Unit"], "Week 2": ["unity"]}


# ======================================================================
# Step B: blank rows / blank lines separate chapters; strict word counts
# ======================================================================
def column_a(rows):
    return [[r] if r is not None else [None] for r in rows]


def chapters_of(res):
    return [[w.text for w in c.words] for c in res.bank.chapters]


def test_spec_example_blank_row_splits_chapters_in_excel():
    rows = ["APPLE", "MANGO", "BANANA", "TIGER", "LION", "MONKEY", None, "ROSE", "LOTUS", "SUNFLOWER"]
    res = import_file("w.xlsx", xlsx_bytes({"Sheet1": column_a(rows)}))
    assert chapters_of(res) == [["APPLE", "MANGO", "BANANA", "TIGER", "LION", "MONKEY"],
                                ["ROSE", "LOTUS", "SUNFLOWER"]]
    assert [c.title for c in res.bank.chapters] == ["Chapter 1", "Chapter 2"]
    # blank row 7 is preserved in the numbering: chapter 2 starts at row 8
    assert res.bank.chapters[1].words[0].source == "Sheet1!A8"
    assert res.layout == "blocks"


def test_blank_row_edge_cases_excel():
    rows = [None, None, "a1", "a2", None, None, None, "   ", "b1", "ice cream", "b3", None, None]
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(rows)}))
    # leading/trailing blanks ignored, runs of blanks (incl. whitespace-only) = ONE separator,
    # a cell with a space inside is a word, not a separator
    assert chapters_of(res) == [["a1", "a2"], ["b1", "ice cream", "b3"]]
    assert res.bank.chapters[1].words[1].source == "S!A10"


def test_surrounding_spaces_trimmed_but_raw_kept():
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(["  apple  ", "mango "])}))
    w = res.bank.chapters[0].words[0]
    assert w.text == "apple" and w.raw == "  apple  "


def test_csv_blank_rows_split_chapters_and_keep_row_numbers():
    res = import_file("w.csv", b"APPLE\nMANGO\n\nROSE\n   \n\nLOTUS\n")
    assert chapters_of(res) == [["APPLE", "MANGO"], ["ROSE"], ["LOTUS"]]
    assert res.bank.chapters[2].words[0].source == "row 7"


def test_txt_blank_lines_split_chapters_crlf_and_whitespace_lines():
    res = import_file("w.txt", b"APPLE\r\nMANGO\r\n\r\n\r\n  \r\nROSE\r\nLOTUS\r\n")
    assert chapters_of(res) == [["APPLE", "MANGO"], ["ROSE", "LOTUS"]]
    assert res.layout == "txt-blocks"


def test_plain_word_list_with_chapterlike_words_is_not_read_as_headings():
    res = import_file("w.txt", b"Level\nDay\nBook\n\nPart\nUnit\n")
    assert chapters_of(res) == [["Level", "Day", "Book"], ["Part", "Unit"]]


def test_header_row_skipped_with_notice_and_extra_columns_warned():
    rows = [["Words", "Notes"], ["apple", "fruit"], ["mango", None]]
    res = import_file("w.xlsx", xlsx_bytes({"S": rows}))
    assert chapters_of(res) == [["apple", "mango"]]
    assert "header_row_skipped" in codes(res)
    extra = [i for i in res.issues if i.code == "extra_columns_ignored"]
    assert len(extra) == 1 and extra[0].source == "S!B1" and "2 cell(s)" in extra[0].message and extra[0].severity == "warning"


def test_multiple_sheets_all_by_default_or_pick_one():
    wb = {"Fruits": column_a(["a", "b", None, "c"]), "Animals": column_a(["x", "y"])}
    data = xlsx_bytes(wb)
    allres = import_file("w.xlsx", data)
    assert chapters_of(allres) == [["a", "b"], ["c"], ["x", "y"]]
    assert "multiple_sheets" in codes(allres)
    assert [(s["name"], s["imported"]) for s in allres.sheets] == [("Fruits", True), ("Animals", True)]
    one = import_file("w.xlsx", data, ImportOptions(sheet="Animals"))
    assert chapters_of(one) == [["x", "y"]]
    assert [(s["name"], s["imported"]) for s in one.sheets] == [("Fruits", False), ("Animals", True)]
    with pytest.raises(ImportError_, match="not found"):
        import_file("w.xlsx", data, ImportOptions(sheet="Nope"))


def test_blank_cells_with_only_trailing_empty_rows():
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(["a", "b", None, None, None])}))
    assert chapters_of(res) == [["a", "b"]]


# ---------------------------------------------------------- strict counts
def alpha(n):
    out = ""
    while True:
        n, r = divmod(n, 26)
        out = chr(97 + r) + out
        if n == 0:
            return out
        n -= 1


def book(counts):
    rows = []
    for ci, n in enumerate(counts):
        rows += [f"c{alpha(ci)}w{alpha(i)}" for i in range(n)] + [None]
    return rows


def test_all_chapters_correct_is_ready():              # acceptance test 1
    rows = book([20] * 10)
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(rows)}), expected_words=20)
    s = res.summary()
    assert (s["chapters"], s["words"], s["valid_chapters"], s["invalid_chapters"]) == (10, 200, 10, 0)
    assert res.ready and not [i for i in res.issues if i.code == "wrong_word_count"]


def test_txt_ten_chapters_counts():                    # acceptance test 2
    txt = "\n\n".join("\n".join(f"c{alpha(c)}w{alpha(i)}" for i in range(20)) for c in range(10))
    res = import_file("w.txt", txt.encode(), expected_words=20)
    assert [len(c.words) for c in res.bank.chapters] == [20] * 10 and res.ready


def test_short_chapter_blocks_with_exact_message():    # acceptance test 3
    counts = [20, 20, 18, 20, 20, 20, 20, 20, 20, 20]
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(book(counts))}), expected_words=20)
    errs = [i for i in res.issues if i.code == "wrong_word_count"]
    assert len(errs) == 1
    e = errs[0]
    assert e.chapter == "Chapter 3" and e.chapter_index == 2 and (e.expected, e.actual) == (20, 18)
    assert e.message == "Chapter 3 has 18 words. Expected 20. Missing 2."
    assert not res.ready and res.summary()["invalid_chapters"] == 1 and res.summary()["valid_chapters"] == 9
    with pytest.raises(ImportValidationError):
        res.bank.to_chapters(expected_words=20)


def test_extra_words_flagged_and_never_removed():      # acceptance test 4
    res = import_file("w.xlsx", xlsx_bytes({"S": column_a(book([22, 20]))}), expected_words=20)
    e = [i for i in res.issues if i.code == "wrong_word_count"]
    assert len(e) == 1 and e[0].message == "Chapter 1 has 22 words. Expected 20. Extra 2."
    assert [len(c.words) for c in res.bank.chapters] == [22, 20]        # nothing removed, nothing added
    assert not res.ready


def test_singular_wording_and_no_check_when_unset():
    res = import_file("w.txt", b"a\n\nb\nc\n", expected_words=2)
    msgs = [i.message for i in res.issues if i.code == "wrong_word_count"]
    assert msgs == ["Chapter 1 has 1 word. Expected 2. Missing 1."]
    assert not [i for i in import_file("w.txt", b"a\n\nb\nc\n").issues if i.code == "wrong_word_count"]


def test_count_includes_invalid_and_duplicate_rows_but_reports_them_separately():
    res = import_file("w.txt", b"apple\nApple\n12!\nmango\n", expected_words=4)
    assert not [i for i in res.issues if i.code == "wrong_word_count"]    # 4 rows = 4
    assert {"duplicate_in_chapter", "invalid_word"} <= set(codes(res))
    assert all(i.chapter_index == 0 for i in res.issues if i.blocking)


def test_fixing_the_count_in_app_clears_the_error_without_hidden_changes():
    res = import_file("w.txt", b"aone\natwo\n\nbone\n", expected_words=2)
    bank = res.bank
    with pytest.raises(ImportValidationError):
        bank.to_chapters(expected_words=2)
    bank.add_word(bank.chapters[1], "btwo")                # user adds the missing word explicitly
    assert bank.to_chapters(expected_words=2) == [("Chapter 1", ["aone", "atwo"]), ("Chapter 2", ["bone", "btwo"])]


def test_import_thousand_chapters_is_fast():
    import time
    rows = book([20] * 1000)
    data = xlsx_bytes({"S": column_a(rows)})
    t = time.time()
    res = import_file("w.xlsx", data, expected_words=20)
    assert res.summary()["chapters"] == 1000 and res.ready
    assert time.time() - t < 15


def test_lines_layout_with_and_without_first_line_title():
    txt = (
        b"Fruits\nAPPLE\nMANGO\n\n"
        b"Animals\nTIGER\nLION\n\n"
        b"Space\nPLANET\nGALAXY\n"
    )
    # Title ENABLED: first line of each chapter is chapter title (not counted as a word)
    with_title = import_file("w.txt", txt, ImportOptions(layout="lines", first_line_title=True),
                             expected_words=2)
    assert with_title.ready
    assert with_title.summary()["chapters"] == 3
    assert with_title.summary()["words"] == 6
    assert [(c.title, [w.text for w in c.words]) for c in with_title.bank.chapters] == [
        ("Fruits", ["APPLE", "MANGO"]),
        ("Animals", ["TIGER", "LION"]),
        ("Space", ["PLANET", "GALAXY"]),
    ]
    assert [c.title_entry.text for c in with_title.bank.chapters] == ["Fruits", "Animals", "Space"]

    # Title DISABLED: every line is a word
    no_title = import_file("w.txt", txt, ImportOptions(layout="lines", first_line_title=False),
                           expected_words=3)
    assert no_title.ready
    assert no_title.summary()["chapters"] == 3
    assert no_title.summary()["words"] == 9
    assert [(c.title, [w.text for w in c.words]) for c in no_title.bank.chapters] == [
        ("Chapter 1", ["Fruits", "APPLE", "MANGO"]),
        ("Chapter 2", ["Animals", "TIGER", "LION"]),
        ("Chapter 3", ["Space", "PLANET", "GALAXY"]),
    ]
    assert all(c.title_entry is None for c in no_title.bank.chapters)


def test_lines_layout_never_skips_words_header_or_splits_commas():
    txt = b"Words\nICE CREAM\n"
    res = import_file("w.txt", txt, ImportOptions(layout="lines", first_line_title=False),
                      expected_words=2)
    assert [w.text for w in res.bank.chapters[0].words] == ["Words", "ICE CREAM"]
    assert res.ready

