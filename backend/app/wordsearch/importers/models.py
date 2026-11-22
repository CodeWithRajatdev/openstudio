"""Word bank: chapters of words with provenance, validation and editing.

Principles: original input is preserved (`raw`), nothing is dropped silently,
problems are reported as Issues, and generation input is only produced when
blocking errors have been resolved by the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.wordsearch.engine.normalize import InvalidWordError, NormalizeRules, normalize_word

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass
class Issue:
    severity: str            # error | warning | info
    code: str
    message: str
    chapter: Optional[str] = None
    word_id: Optional[int] = None
    source: Optional[str] = None     # "row 12", "line 4", "Sheet1!B5"
    chapter_index: Optional[int] = None   # 0-based position of the chapter
    expected: Optional[int] = None        # wrong_word_count: required words
    actual: Optional[int] = None          # wrong_word_count: words found

    @property
    def blocking(self) -> bool:
        return self.severity == ERROR


@dataclass
class WordEntry:
    id: int
    raw: str                 # exactly what was in the file (never modified)
    text: str                # current editable value
    source: Optional[str] = None

    @property
    def edited(self) -> bool:
        return self.text != self.raw.strip()


@dataclass
class Chapter:
    title: str
    words: list[WordEntry] = field(default_factory=list)
    # The file line the title was read from (first line of the chapter), if any.
    title_entry: Optional[WordEntry] = None


def chapter_label(index: int, title: str) -> str:
    """How a chapter is named in messages: "Chapter 3", or "Chapter 3 (Fruits)"."""
    base = f"Chapter {index + 1}"
    t = (title or "").strip()
    return base if not t or t == base else f"{base} ({t})"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class ImportValidationError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__(f"{len(issues)} blocking issue(s): " +
                         "; ".join(i.message for i in issues[:5]) +
                         (" ..." if len(issues) > 5 else ""))


class WordBank:
    def __init__(self) -> None:
        self.chapters: list[Chapter] = []
        self._next_id = 1

    # ------------------------------------------------------------ building
    def _new_id(self) -> int:
        i, self._next_id = self._next_id, self._next_id + 1
        return i

    def get_chapter(self, title: str) -> Optional[Chapter]:
        return next((c for c in self.chapters if c.title == title), None)

    def add_chapter(self, title: str, words: Optional[list[str]] = None) -> Chapter:
        ch = Chapter(title=title)
        self.chapters.append(ch)
        for w in words or []:
            self.add_word(ch, w)
        return ch

    def add_word(self, chapter: Chapter | str, text: str, raw: Optional[str] = None,
                 source: Optional[str] = None) -> WordEntry:
        ch = chapter if isinstance(chapter, Chapter) else self._require(chapter)
        entry = WordEntry(id=self._new_id(), raw=text if raw is None else raw,
                          text=text.strip(), source=source)
        ch.words.append(entry)
        return entry

    def _require(self, title: str) -> Chapter:
        ch = self.get_chapter(title)
        if ch is None:
            raise KeyError(f"no chapter named {title!r}")
        return ch

    # ------------------------------------------------------------- editing
    def remove_chapter(self, title: str) -> Chapter:
        ch = self._require(title)
        self.chapters.remove(ch)
        return ch

    def rename_chapter(self, old: str, new: str) -> None:
        self._require(old).title = new

    def find_word(self, word_id: int) -> tuple[Chapter, WordEntry]:
        for ch in self.chapters:
            for w in ch.words:
                if w.id == word_id:
                    return ch, w
        raise KeyError(f"no word with id {word_id}")

    def edit_word(self, word_id: int, new_text: str) -> None:
        self.find_word(word_id)[1].text = new_text.strip()

    def delete_word(self, word_id: int) -> WordEntry:
        ch, w = self.find_word(word_id)
        ch.words.remove(w)
        return w

    def remove_duplicates(self, rules: Optional[NormalizeRules] = None
                          ) -> list[tuple[str, WordEntry]]:
        """Explicit user action: drop later duplicates inside each chapter.
        Returns exactly what was removed so the UI can show/undo it."""
        removed = []
        for ch in self.chapters:
            seen: set[str] = set()
            for w in list(ch.words):
                key = _norm_or_none(w.text, rules)
                if key is None:
                    continue
                if key in seen:
                    ch.words.remove(w)
                    removed.append((ch.title, w))
                else:
                    seen.add(key)
        return removed

    # ---------------------------------------------------------- validation
    def validate(self, rules: Optional[NormalizeRules] = None, *,
                 check_cross_chapter: bool = False,
                 max_word_length: Optional[int] = None,
                 expected_words: Optional[int] = None) -> list[Issue]:
        """expected_words: every chapter must contain exactly this many entries.
        The count includes every row; invalid and duplicate entries are
        reported separately and nothing is ever removed or added."""
        issues: list[Issue] = []
        titles: dict[str, int] = {}
        for ch in self.chapters:
            titles[ch.title] = titles.get(ch.title, 0) + 1
        for t, n in titles.items():
            if n > 1:
                issues.append(Issue(WARNING, "duplicate_chapter_title",
                                    f"Chapter title {t!r} appears {n} times.", chapter=t))
        first_seen: dict[str, str] = {}
        for ci, ch in enumerate(self.chapters):
            start = len(issues)
            name = chapter_label(ci, ch.title)
            if expected_words is not None and len(ch.words) != expected_words:
                n, diff = len(ch.words), expected_words - len(ch.words)
                detail = f"Missing {diff}." if diff > 0 else f"Extra {-diff}."
                issues.append(Issue(
                    ERROR, "wrong_word_count",
                    f"{name} has {_plural(n, 'word')}. Expected {expected_words}. {detail}",
                    chapter=ch.title, expected=expected_words, actual=n))
            if not ch.words:
                issues.append(Issue(WARNING, "empty_chapter",
                                    f"{name} has no words.", chapter=ch.title))
            in_chapter: dict[str, WordEntry] = {}
            for wn, w in enumerate(ch.words, 1):
                if not w.text.strip():
                    issues.append(Issue(ERROR, "blank_word",
                                        f"{name}, word {wn} is empty.", ch.title, w.id, w.source))
                    continue
                key = _norm_or_none(w.text, rules)
                if key is None:
                    issues.append(Issue(
                        ERROR, "invalid_word",
                        f"{name}: \"{w.text}\" has characters that cannot go in a puzzle grid.",
                        ch.title, w.id, w.source))
                    continue
                if max_word_length and len(key) > max_word_length:
                    issues.append(Issue(
                        ERROR, "word_too_long",
                        f"{name}: \"{w.text}\" has {len(key)} letters. The limit is "
                        f"{max_word_length}.", ch.title, w.id, w.source))
                if key in in_chapter:
                    issues.append(Issue(
                        ERROR, "duplicate_in_chapter",
                        f"{name}: \"{w.text}\" is the same word as \"{in_chapter[key].text}\". "
                        "Each word can appear only once in a chapter.",
                        ch.title, w.id, w.source))
                else:
                    in_chapter[key] = w
                if check_cross_chapter:
                    other = first_seen.get(key)
                    if other is not None and other != name:
                        issues.append(Issue(
                            WARNING, "duplicate_across_chapters",
                            f"{name}: \"{w.text}\" also appears in {other}.",
                            ch.title, w.id, w.source))
                    first_seen.setdefault(key, name)
            for iss in issues[start:]:
                iss.chapter_index = ci
        return issues

    # ------------------------------------------------------------- output
    def to_chapters(self, rules: Optional[NormalizeRules] = None, **validate_kwargs
                    ) -> list[tuple[str, list[str]]]:
        """[(title, words)] for generate_chapters(). Refuses while blocking
        issues remain, so no word is ever silently skipped."""
        blocking = [i for i in self.validate(rules, **validate_kwargs) if i.blocking]
        if blocking:
            raise ImportValidationError(blocking)
        return [(c.title, [w.text for w in c.words]) for c in self.chapters]

    def stats(self) -> dict:
        return {"chapters": len(self.chapters),
                "words": sum(len(c.words) for c in self.chapters)}


def _norm_or_none(text: str, rules: Optional[NormalizeRules]) -> Optional[str]:
    try:
        return normalize_word(text, rules)
    except InvalidWordError:
        return None
