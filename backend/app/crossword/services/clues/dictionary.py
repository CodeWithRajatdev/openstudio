"""Dictionary providers (WordNet, custom JSONL) and gloss-to-clue conversion."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ...config import Settings
from ...engine.preprocess import normalize_answer
from .validator import validate_clue

_PAREN_RE = re.compile(r"\([^()]*\)")
_SPACE_RE = re.compile(r"\s+")

DIFFICULTY_WORD_CAPS: dict[str, int] = {
    "easy": 9,
    "medium": 14,
    "hard": 18,
}


def gloss_to_clue(gloss: str, answer: str, difficulty: str = "medium") -> Optional[str]:
    """Convert a dictionary gloss into a clean crossword clue or return None if unsuitable."""
    text = (gloss or "").split(";", 1)[0]
    # Remove nested or flat parentheticals
    prev = None
    while prev != text:
        prev = text
        text = _PAREN_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip(" \t\r\n.,;:-")
    if not text:
        return None

    text = text[0].upper() + text[1:] + "."
    cap = DIFFICULTY_WORD_CAPS.get(difficulty, 14)
    if len(text.split()) > cap:
        return None

    if not validate_clue(text, answer, max_words=cap).valid:
        return None
    return text


class DictionaryProvider(ABC):
    @abstractmethod
    def lookup(self, display: str, answer: str, difficulty: str = "medium") -> Optional[str]:
        """Return a formatted, validated clue if an exact-lemma definition fits, else None."""

    @abstractmethod
    def hints(self, display: str, answer: str, limit: int = 3) -> list[str]:
        """Return raw dictionary definitions to pass as AI context."""

    def lookup_alternatives(
        self, display: str, answer: str, difficulty: str = "medium", limit: int = 3
    ) -> list[str]:
        """Return up to `limit` distinct validated clues for the word."""
        single = self.lookup(display, answer, difficulty=difficulty)
        return [single] if single else []


class NullDictionaryProvider(DictionaryProvider):
    def lookup(self, display: str, answer: str, difficulty: str = "medium") -> Optional[str]:
        return None

    def hints(self, display: str, answer: str, limit: int = 3) -> list[str]:
        return []


class WordNetDictionaryProvider(DictionaryProvider):
    def _matching_synsets(self, display: str, answer: str):
        try:
            from nltk.corpus import wordnet as wn
        except LookupError:
            return []

        raw_term = (display or answer).strip().lower().replace(" ", "_").replace("-", "_")
        target_upper = answer.upper()

        try:
            synsets = wn.synsets(raw_term)
        except LookupError:
            return []

        matched = []
        for syn in synsets:
            # Skip proper-noun instances (e.g. countries, people, places)
            if syn.instance_hypernyms():
                continue
            # Require an exact non-capitalized lemma match (reject inflected forms like APPLES -> apple)
            exact_common = False
            for lemma in syn.lemmas():
                lname = lemma.name()
                if lname and lname[0].isupper():
                    continue
                norm, _ = normalize_answer(lname.replace("_", ""))
                if norm == target_upper:
                    exact_common = True
                    break
            if exact_common:
                matched.append(syn)
        return matched

    def lookup(self, display: str, answer: str, difficulty: str = "medium") -> Optional[str]:
        for syn in self._matching_synsets(display, answer):
            clue = gloss_to_clue(syn.definition(), answer, difficulty=difficulty)
            if clue:
                return clue
        return None

    def lookup_alternatives(
        self, display: str, answer: str, difficulty: str = "medium", limit: int = 3
    ) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for syn in self._matching_synsets(display, answer):
            clue = gloss_to_clue(syn.definition(), answer, difficulty=difficulty)
            if clue and clue not in seen:
                seen.add(clue)
                out.append(clue)
            if len(out) >= limit:
                break
        return out

    def hints(self, display: str, answer: str, limit: int = 3) -> list[str]:
        out: list[str] = []
        for syn in self._matching_synsets(display, answer):
            defn = (syn.definition() or "").strip()
            if defn and defn not in out:
                out.append(defn)
            if len(out) >= limit:
                break
        return out


class JsonlDictionaryProvider(DictionaryProvider):
    def __init__(self, path: str | Path) -> None:
        self._entries: dict[str, list[str]] = {}
        p = Path(path)
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                raw_word = obj.get("word") or obj.get("answer") or ""
                norm, _ = normalize_answer(raw_word)
                if not norm:
                    continue
                if obj.get("proper_noun"):
                    continue
                defs: list[str] = []
                if isinstance(obj.get("definitions"), list):
                    defs.extend(str(d) for d in obj["definitions"] if d)
                elif obj.get("definition") or obj.get("gloss"):
                    defs.append(str(obj.get("definition") or obj.get("gloss")))
                if defs:
                    self._entries.setdefault(norm, []).extend(defs)

    def lookup(self, display: str, answer: str, difficulty: str = "medium") -> Optional[str]:
        for defn in self._entries.get(answer.upper(), []):
            clue = gloss_to_clue(defn, answer, difficulty=difficulty)
            if clue:
                return clue
        return None

    def lookup_alternatives(
        self, display: str, answer: str, difficulty: str = "medium", limit: int = 3
    ) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for defn in self._entries.get(answer.upper(), []):
            clue = gloss_to_clue(defn, answer, difficulty=difficulty)
            if clue and clue not in seen:
                seen.add(clue)
                out.append(clue)
            if len(out) >= limit:
                break
        return out

    def hints(self, display: str, answer: str, limit: int = 3) -> list[str]:
        return list(self._entries.get(answer.upper(), []))[:limit]


def get_dictionary_provider(settings: Settings) -> DictionaryProvider:
    kind = (settings.dictionary_provider or "wordnet").strip().lower()
    if kind == "none":
        return NullDictionaryProvider()
    if kind == "jsonl":
        if not settings.dictionary_jsonl_path:
            return NullDictionaryProvider()
        return JsonlDictionaryProvider(settings.dictionary_jsonl_path)
    return WordNetDictionaryProvider()
