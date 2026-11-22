from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Optional

from .models import INFO, WARNING, Issue, WordBank, WordEntry

CHAPTER_KEYS = {"chapter", "chapter name", "chapter title", "title", "unit", "topic",
                "section", "category", "theme", "lesson", "puzzle", "puzzle title"}
BLOCK_HEADERS = {"word", "words", "word list", "wordlist"}
WORD_KEYS = {"word", "words", "term", "terms", "vocabulary", "entry", "answer"}


@dataclass
class ImportOptions:
    layout: str = "auto"          # auto | lines | blocks | long | wide | single
    default_chapter_title: str = "Chapter 1"
    split_commas: bool = True     # TXT: "apple, mango" -> two words
    sheet: Optional[str] = None   # XLSX: a sheet name, or None / "__all__" for every sheet
    max_bytes: int = 25 * 1024 * 1024
    # layout "lines" only: the first line of every chapter is the chapter title.
    first_line_title: bool = False


def _cell(v) -> Optional[str]:
    """Raw cell text, or None when empty. Numbers keep a clean text form."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v)
    return s if s.strip() else None


def decode_bytes(data: bytes, issues: list[Issue]) -> str:
    for enc in ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    issues.append(Issue(WARNING, "encoding_fallback",
                        "File is not valid UTF-8; decoded as Windows-1252. "
                        "Check accented characters."))
    return data.decode("cp1252", errors="replace")


# ------------------------------------------------------------ strict lines

class _LineChapters:
    """The studio's file rules, shared by TXT, CSV and XLSX:

    * one line (row) = one word, taken exactly as written (only outer spaces trimmed);
    * a blank line / blank row = the chapter ends here (runs of blanks count once);
    * if `first_line_title`, the FIRST line of each chapter is its title, not a word.

    Nothing is ever split, merged, skipped or added."""

    def __init__(self, bank: WordBank, opts: ImportOptions) -> None:
        self.bank, self.opts = bank, opts
        self.current = None

    def blank(self) -> None:
        self.current = None

    def line(self, text: str, source: str) -> None:
        if self.current is None:
            n = len(self.bank.chapters) + 1
            self.current = self.bank.add_chapter(f"Chapter {n}")
            if self.opts.first_line_title:
                self.current.title = text.strip()
                self.current.title_entry = WordEntry(id=self.bank._new_id(), raw=text,
                                                     text=text.strip(), source=source)
                return
        self.bank.add_word(self.current, text, raw=text, source=source)


def parse_lines_rows(rows: list[list], bank: WordBank, issues: list[Issue],
                     opts: ImportOptions, sheet: Optional[str] = None,
                     state: Optional[_LineChapters] = None) -> None:
    """Column A of a CSV / worksheet under the strict line rules."""
    st = state or _LineChapters(bank, opts)
    st.blank()                                # a new sheet always starts a new chapter
    extra: list[str] = []

    def ref(r: int, c: int = 0) -> str:
        col = chr(65 + c) if c < 26 else f"col {c + 1}"
        return f"{sheet}!{col}{r + 1}" if sheet else f"row {r + 1}"

    for r, row in enumerate(rows):
        a = _cell(row[0]) if row else None
        if len(row) > 1:
            extra += [ref(r, c) for c in range(1, len(row)) if _cell(row[c]) is not None]
        if a is None:
            st.blank()
        else:
            st.line(a, ref(r))
    if extra:
        issues.append(Issue(WARNING, "extra_columns_ignored",
                            f"Only column A is read. {len(extra)} filled cell(s) in other columns "
                            f"were not imported (first one: {extra[0]}).", source=extra[0]))


def parse_lines_txt(text: str, bank: WordBank, opts: ImportOptions) -> None:
    st = _LineChapters(bank, opts)
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            st.line(line, f"line {n}")
        else:
            st.blank()


# ----------------------------------------------------------------- tables

def parse_blocks(rows: list[list], bank: WordBank, issues: list[Issue], opts: ImportOptions,
                 sheet: Optional[str] = None) -> int:
    """Column A holds the words; a blank row starts a new chapter.

    Row numbers are preserved (blank rows are real rows), runs of blank rows
    count as one separator, leading/trailing blanks are ignored, and a cell
    containing spaces between words ("ice cream") is a word, not a separator.
    Returns the number of chapters added."""
    def ref(r: int, c: int = 0) -> str:
        col = chr(65 + c)
        return f"{sheet}!{col}{r + 1}" if sheet else f"row {r + 1}"

    current = None
    added = 0
    first_data = True
    extra: list[str] = []
    for r, row in enumerate(rows):
        a = _cell(row[0]) if row else None
        if len(row) > 1:
            extra += [ref(r, c) for c in range(1, len(row)) if _cell(row[c]) is not None]
        if a is None:
            current = None            # blank row (or whitespace only) ends the chapter
            continue
        text = a.strip()
        if first_data and text.lower() in BLOCK_HEADERS:
            issues.append(Issue(INFO, "header_row_skipped",
                                f"Row {r + 1} ({text!r}) looks like a column header and was not "
                                "imported as a word.", source=ref(r)))
            first_data = False
            continue
        first_data = False
        if current is None:
            current = bank.add_chapter(f"Chapter {len(bank.chapters) + 1}")
            added += 1
        bank.add_word(current, a, raw=a, source=ref(r))
    if extra:
        issues.append(Issue(WARNING, "extra_columns_ignored",
                            f"Only column A was read; {len(extra)} cell(s) in other columns were "
                            f"ignored (first: {extra[0]}). Use layout 'Column per chapter' or "
                            "'Chapter + Word columns' if that is how the file is organised.",
                            source=extra[0]))
    return added

def parse_table(rows: list[list], bank: WordBank, issues: list[Issue],
                opts: ImportOptions, sheet: Optional[str] = None,
                single_title: Optional[str] = None) -> str:
    """Shared by CSV and each XLSX sheet. Returns the layout actually used."""
    if opts.layout == "lines":
        parse_lines_rows(rows, bank, issues, opts, sheet)
        return "lines"

    def loc(r: int, c: int) -> str:
        col = ""
        n = c + 1
        while n:
            n, rem = divmod(n - 1, 26)
            col = chr(65 + rem) + col
        return f"{sheet}!{col}{r + 1}" if sheet else f"row {r + 1}, col {c + 1}"

    # drop wholly empty rows but keep original row numbers
    indexed = [(i, r) for i, r in enumerate(rows) if any(_cell(x) for x in r)]
    if not indexed:
        issues.append(Issue(WARNING, "empty_input",
                            f"{'Sheet ' + repr(sheet) if sheet else 'File'} contains no data."))
        return "empty"
    width = max(len(r) for _, r in indexed)
    header = [(_cell(x) or "").strip().lower() for x in indexed[0][1]]
    layout = opts.layout

    chap_col = next((i for i, h in enumerate(header) if h in CHAPTER_KEYS), None)
    word_col = next((i for i, h in enumerate(header) if h in WORD_KEYS), None)

    if layout == "auto":
        layout = "long" if (chap_col is not None and word_col is not None) else "blocks"

    if layout == "blocks":
        parse_blocks(rows, bank, issues, opts, sheet)
        return "blocks"

    if layout == "long":
        if chap_col is None or word_col is None:
            raise ValueError("Long layout needs a chapter column and a word column "
                             "(e.g. headers 'Chapter' and 'Word').")
        for r, row in indexed[1:]:
            title = _cell(row[chap_col]) if chap_col < len(row) else None
            word = _cell(row[word_col]) if word_col < len(row) else None
            if word is None:
                if title:
                    issues.append(Issue(INFO, "blank_entry",
                                        f"Blank word for chapter {title.strip()!r}.",
                                        chapter=title.strip(), source=loc(r, word_col)))
                continue
            if title is None:
                issues.append(Issue(WARNING, "missing_chapter",
                                    f"{word!r} has no chapter; placed under "
                                    f"{opts.default_chapter_title!r}.", source=loc(r, word_col)))
                title = opts.default_chapter_title
            ch = bank.get_chapter(title.strip()) or bank.add_chapter(title.strip())
            bank.add_word(ch, word, raw=word, source=loc(r, word_col))
        return "long"

    if layout == "single":
        col = word_col if word_col is not None else 0
        start = 1 if word_col is not None else 0
        title = single_title or opts.default_chapter_title
        ch = bank.add_chapter(title)
        for r, row in indexed[start:]:
            word = _cell(row[col]) if col < len(row) else None
            if word is not None:
                bank.add_word(ch, word, raw=word, source=loc(r, col))
        return "single"

    if layout == "wide":
        head_row, head = indexed[0]
        body = indexed[1:]
        for c in range(width):
            title = _cell(head[c]) if c < len(head) else None
            if title is None:
                col_words = [(r, row[c]) for r, row in body if c < len(row) and _cell(row[c])]
                if col_words:
                    issues.append(Issue(WARNING, "untitled_column",
                                        f"Column {c + 1} has words but no header; "
                                        f"titled 'Column {c + 1}'.", source=loc(head_row, c)))
                    title = f"Column {c + 1}"
                else:
                    continue
            ch = bank.add_chapter(title.strip())
            cells = [(r, _cell(row[c]) if c < len(row) else None) for r, row in body]
            last = max((i for i, (_, v) in enumerate(cells) if v is not None), default=-1)
            for i, (r, v) in enumerate(cells[:last + 1]):
                if v is None:
                    issues.append(Issue(INFO, "blank_entry",
                                        f"Blank cell inside chapter {title.strip()!r}.",
                                        chapter=title.strip(), source=loc(r, c)))
                else:
                    bank.add_word(ch, v, raw=v, source=loc(r, c))
        return "wide"

    raise ValueError(f"unknown layout {opts.layout!r}")


def parse_csv(text: str, bank: WordBank, issues: list[Issue], opts: ImportOptions) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return parse_table(rows, bank, issues, opts)


def parse_xlsx(data: bytes, bank: WordBank, issues: list[Issue], opts: ImportOptions
               ) -> tuple[str, list[dict]]:
    """Returns (layout, sheets). `sheets` lists every worksheet so the UI can offer a choice."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    names = [ws.title for ws in wb.worksheets]
    chosen = opts.sheet if opts.sheet not in (None, "", "__all__") else None
    if chosen is not None and chosen not in names:
        wb.close()
        raise ValueError(f"Worksheet {chosen!r} not found. Available: {', '.join(names)}.")
    used = set()
    sheets = []
    for ws in wb.worksheets:
        hidden = ws.sheet_state != "visible"
        sheets.append({"name": ws.title, "hidden": hidden, "imported": chosen in (None, ws.title)})
        if chosen is not None and ws.title != chosen:
            continue
        try:
            ws.reset_dimensions()          # some writers omit the sheet dimension
        except Exception:
            pass
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if hidden:
            issues.append(Issue(INFO, "hidden_sheet",
                                f"Sheet {ws.title!r} is hidden but was imported."))
        used.add(parse_table(rows, bank, issues, opts, sheet=ws.title, single_title=ws.title))
    wb.close()
    if chosen is None and len(names) > 1:
        issues.append(Issue(INFO, "multiple_sheets",
                            f"All {len(names)} worksheets were imported in order: {', '.join(names)}."))
    return ("+".join(sorted(used)) or "empty"), sheets


# -------------------------------------------------------------------- txt
_HEAD_RES = [
    re.compile(r"^\s*#{1,6}\s*(?P<t>.+?)\s*#*\s*$"),
    re.compile(r"^\s*\[(?P<t>.+)\]\s*$"),
    # keyword must be followed by a number, roman numeral or ':' '-' '.' so that
    # ordinary words like "Book", "Level" or "Day" stay words.
    re.compile(r"^\s*(?P<t>(?:chapter|unit|lesson|section|week|day|part|book|level)"
               r"(?:\s*\d+|\s+[ivxlc]+\b|\s*[:\-\u2013.]).*?)\s*$", re.I),
    re.compile(r"^\s*(?P<t>[^,;:]+?)\s*:\s*$"),
]


def _heading(line: str, strict: bool = False) -> Optional[str]:
    """strict=True only accepts '# X', '[X]' and 'Chapter 1'-style lines, so a plain
    word list is never mistaken for a headed one."""
    for rx in (_HEAD_RES[:3] if strict else _HEAD_RES):
        m = rx.match(line)
        if m:
            return m.group("t").strip().rstrip(":").strip()
    return None


def parse_txt(text: str, bank: WordBank, issues: list[Issue], opts: ImportOptions) -> str:
    if opts.layout == "lines":
        parse_lines_txt(text, bank, opts)
        return "txt-lines"
    lines = text.splitlines()
    has_headings = opts.layout != "blocks" and any(_heading(ln, strict=True) for ln in lines if ln.strip())
    current = None
    block_no = 0
    prev_blank = True
    for n, line in enumerate(lines, 1):
        if not line.strip():
            prev_blank = True
            continue
        if has_headings:
            t = _heading(line)
            if t:
                current = bank.add_chapter(t)
                prev_blank = False
                continue
            if current is None:
                current = bank.add_chapter(opts.default_chapter_title)
                issues.append(Issue(WARNING, "words_before_heading",
                                    "Words appear before the first heading; placed under "
                                    f"{opts.default_chapter_title!r}.", source=f"line {n}"))
        else:
            # no headings: blank-line-separated blocks are chapters
            if prev_blank:
                block_no += 1
                current = bank.add_chapter(f"Chapter {block_no}")
        prev_blank = False
        parts = re.split(r"[;,\t]", line) if opts.split_commas else [line]
        for p in parts:
            if p.strip():
                bank.add_word(current, p, raw=p, source=f"line {n}")
    if not has_headings and block_no == 1:
        bank.chapters[-1].title = opts.default_chapter_title
    return "txt-headings" if has_headings else "txt-blocks"
