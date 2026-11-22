"""Word normalization. Nothing is dropped silently: every rejection is reported."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Union

from .types import WordInput

_STRIP = re.compile(r"[\s\-'’.]")


def normalize_answer(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (answer, problem). Accents are folded; spaces, hyphens, apostrophes removed."""
    text = unicodedata.normalize("NFKD", raw or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _STRIP.sub("", text).upper()
    if not text:
        return None, "empty entry"
    if not re.fullmatch(r"[A-Z]+", text):
        return None, "contains characters other than letters"
    return text, None


def format_enumeration(
    answer: str,
    display: Optional[str] = None,
    style: Union[str, bool] = "formatted",
) -> str:
    """Format crossword answer length enumeration like (3,5), (4-4), or (8).

    style:
    - "formatted" (default): preserves word/hyphen boundaries from display text, e.g. "ice cream" -> "(3,5)"
    - "total" / "simple" / "length" / "total_only": single total letter count, e.g. "(8)"
    - "none" / "off" / "false" / "hidden" / False: empty string
    """
    if style is False or (
        isinstance(style, str) and style.strip().lower() in ("none", "off", "false", "hidden")
    ):
        return ""
    ans = (answer or "").strip()
    if not ans:
        return ""
    if isinstance(style, str) and style.strip().lower() in ("total", "simple", "length", "total_only"):
        return f"({len(ans)})"
    if not display or not display.strip():
        return f"({len(ans)})"

    folded = unicodedata.normalize("NFKD", display.strip())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))

    word_tokens = [tok for tok in re.split(r"\s+", folded) if tok]
    word_parts: list[str] = []
    total_counted = 0

    for token in word_tokens:
        hyphen_subs = [sub for sub in re.split(r"[-–—]+", token) if sub]
        sub_counts: list[str] = []
        for sub in hyphen_subs:
            cleaned = re.sub(r"['’.]", "", sub)
            letter_count = len(re.findall(r"[A-Za-z]", cleaned))
            if letter_count > 0:
                sub_counts.append(str(letter_count))
                total_counted += letter_count
        if sub_counts:
            word_parts.append("-".join(sub_counts))

    if total_counted == len(ans) and word_parts:
        return f"({','.join(word_parts)})"
    return f"({len(ans)})"


@dataclass
class PreprocessResult:
    accepted: list[WordInput] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)


def preprocess_words(
    items: Iterable[Union[str, tuple[str, Any]]],
    min_len: int = 3,
    max_len: int = 30,
) -> PreprocessResult:
    """items: raw strings or (raw, ref) tuples."""
    out = PreprocessResult()
    seen: dict[str, str] = {}
    for item in items:
        raw, ref = (item, None) if isinstance(item, str) else (item[0], item[1])
        answer, problem = normalize_answer(raw)
        if problem is None and answer is not None:
            if len(answer) < min_len:
                problem = f"shorter than the minimum length of {min_len}"
            elif len(answer) > max_len:
                problem = f"longer than the maximum length of {max_len}"
        if problem or answer is None:
            out.rejected.append({"raw": raw, "ref": ref, "reason": problem})
            continue
        if answer in seen:
            out.duplicates.append({"raw": raw, "ref": ref, "answer": answer, "first_seen_as": seen[answer]})
            continue
        seen[answer] = raw
        out.accepted.append(WordInput(answer=answer, ref=ref))
    return out
