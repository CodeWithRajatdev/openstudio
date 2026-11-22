from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Optional

from app.wordsearch.engine.normalize import NormalizeRules

from .models import ERROR, INFO, Issue, WordBank
from .parsers import (ImportOptions, decode_bytes, parse_csv, parse_txt, parse_xlsx)


class ImportError_(ValueError):
    """The file could not be read at all (distinct from per-word issues)."""


@dataclass
class ImportResult:
    filename: str
    fmt: str
    layout: str
    bank: WordBank
    issues: list[Issue] = field(default_factory=list)
    original_bytes: bytes = b""       # preserved untouched for re-import / audit
    sha256: str = ""
    sheets: list = field(default_factory=list)   # XLSX worksheets (for the picker)
    expected_words: Optional[int] = None

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking]

    @property
    def ready(self) -> bool:
        return not self.blocking

    def summary(self) -> dict:
        counts = {s: sum(1 for i in self.issues if i.severity == s)
                  for s in ("error", "warning", "info")}
        bad = {i.chapter_index for i in self.issues if i.blocking and i.chapter_index is not None}
        n = len(self.bank.chapters)
        return {**self.bank.stats(), "format": self.fmt, "layout": self.layout,
                "issues": counts, "ready": self.ready,
                "valid_chapters": n - len(bad), "invalid_chapters": len(bad),
                "expected_words": self.expected_words}


def import_file(filename: str, data: bytes, options: Optional[ImportOptions] = None,
                rules: Optional[NormalizeRules] = None, *,
                check_cross_chapter: bool = False,
                max_word_length: Optional[int] = None,
                expected_words: Optional[int] = None) -> ImportResult:
    opts = options or ImportOptions()
    if len(data) > opts.max_bytes:
        raise ImportError_(f"File is {len(data) / 1e6:.1f} MB; limit is "
                           f"{opts.max_bytes / 1e6:.0f} MB.")
    if not data.strip():
        raise ImportError_("File is empty.")
    ext = PurePath(filename).suffix.lower()
    bank = WordBank()
    issues: list[Issue] = []
    sheets: list = []
    try:
        if ext in (".csv", ".tsv"):
            layout = parse_csv(decode_bytes(data, issues), bank, issues, opts)
            fmt = "csv"
        elif ext == ".txt":
            layout = parse_txt(decode_bytes(data, issues), bank, issues, opts)
            fmt = "txt"
        elif ext in (".xlsx", ".xlsm"):
            layout, sheets = parse_xlsx(data, bank, issues, opts)
            fmt = "xlsx"
        else:
            raise ImportError_(f"Unsupported file type {ext or '(none)'}; "
                               "use .csv, .xlsx or .txt.")
    except ImportError_:
        raise
    except ValueError as e:
        raise ImportError_(str(e)) from e
    except Exception as e:  # corrupt xlsx, etc.
        raise ImportError_(f"Could not read {filename}: {e}") from e

    if not bank.chapters or bank.stats()["words"] == 0:
        raise ImportError_("No words were found in the file.")
    issues.extend(bank.validate(rules, check_cross_chapter=check_cross_chapter,
                                max_word_length=max_word_length,
                                expected_words=expected_words))
    return ImportResult(filename=filename, fmt=fmt, layout=layout, bank=bank,
                        issues=issues, original_bytes=data,
                        sha256=hashlib.sha256(data).hexdigest(), sheets=sheets,
                        expected_words=expected_words)
