"""Clue quality and leak validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_BOILERPLATE_PATTERNS = (
    re.compile(r"^\s*(clue|answer|definition|hint)\s*:", re.IGNORECASE),
    re.compile(r"\b(here is|here's|as an ai|i cannot|certainly|sure,)\b", re.IGNORECASE),
    re.compile(r"\bcrossword clue\b", re.IGNORECASE),
)

_TOKEN_RE = re.compile(r"[A-Za-z]+")


@dataclass
class ClueValidationResult:
    valid: bool
    reasons: list[str] = field(default_factory=list)


def _has_balanced_punctuation(text: str) -> bool:
    pairs = {"(": ")", "[": "]"}
    stack: list[str] = []
    for ch in text:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack.pop() != ch:
                return False
    if stack:
        return False
    if text.count('"') % 2 != 0:
        return False
    return True


def _extract_stems(answer_upper: str) -> set[str]:
    stems = {answer_upper}
    if len(answer_upper) >= 5:
        for suffix in ("IES", "ING", "ED", "ES", "ER", "LY", "S"):
            if answer_upper.endswith(suffix) and len(answer_upper) - len(suffix) >= 3:
                stem = answer_upper[: -len(suffix)]
                if suffix == "IES":
                    stem += "Y"
                stems.add(stem)
        # Common root prefix for >= 5-letter answers
        stems.add(answer_upper[:-1])
    elif len(answer_upper) == 4 and answer_upper.endswith("S"):
        stems.add(answer_upper[:-1])
    return stems


def _leaks_answer(clue_text: str, answer: str) -> bool:
    ans = re.sub(r"[^A-Za-z]", "", answer or "").upper()
    if not ans:
        return False

    tokens = [t.upper() for t in _TOKEN_RE.findall(clue_text)]
    stems = _extract_stems(ans)

    for tok in tokens:
        if tok in stems:
            return True
        if len(ans) >= 4 and ans in tok:
            return True
        if len(tok) >= 4 and tok in ans and len(tok) >= len(ans) - 1:
            return True
        # Check if token is an inflected form of the answer (e.g. APPLES for APPLE)
        for stem in stems:
            if len(stem) >= 4 and tok.startswith(stem) and len(tok) - len(stem) <= 3:
                return True

    joined = "".join(tokens)
    if len(ans) >= 4 and ans in joined:
        return True
    return False


def validate_clue(text: str, answer: str, max_words: int = 25) -> ClueValidationResult:
    reasons: list[str] = []
    cleaned = (text or "").strip()

    if not cleaned:
        return ClueValidationResult(valid=False, reasons=["clue is empty"])

    if len(cleaned) < 2:
        reasons.append("clue is too short")
    if len(cleaned) > 200:
        reasons.append("clue exceeds 200 characters")

    words = cleaned.split()
    if len(words) > max_words:
        reasons.append(f"clue exceeds {max_words} words")

    first_alpha = next((ch for ch in cleaned if ch.isalpha()), None)
    if first_alpha is None or not cleaned.lstrip('"\'([').startswith(first_alpha) or not first_alpha.isupper():
        # Allow starting with a digit (e.g. "12-month period.")
        first_char = cleaned.lstrip('"\'([')[:1]
        if not (first_char.isdigit() or first_char.isupper()):
            reasons.append("clue must start with a capital letter")

    if not _has_balanced_punctuation(cleaned):
        reasons.append("unbalanced quotes or brackets")

    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(cleaned):
            reasons.append("contains AI boilerplate")
            break

    if _leaks_answer(cleaned, answer):
        reasons.append("leaks answer or stem")

    return ClueValidationResult(valid=(len(reasons) == 0), reasons=reasons)


def format_clue_for_render(
    text: Optional[str],
    *,
    capitalization: str = "sentence",
    ending_punctuation: str = "keep",
) -> str:
    """Apply clue capitalization & ending punctuation at render time without mutating stored text."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cap = (capitalization or "sentence").strip().lower()
    if cap in ("uppercase", "upper", "all_caps"):
        cleaned = cleaned.upper()
    elif cap in ("lowercase", "lower"):
        cleaned = cleaned.lower()
    elif cap == "title":
        cleaned = cleaned.title()
    elif cap == "sentence":
        cleaned = cleaned[0].upper() + cleaned[1:]
    # "as_is" / "none" / "keep" -> leave letter casing unchanged

    punct = (ending_punctuation or "keep").strip().lower()
    if punct in ("none", "strip", "off", ""):
        cleaned = cleaned.rstrip(".!?,;:")
    elif punct in ("period", "dot", "."):
        cleaned = cleaned.rstrip(",;:")
        if cleaned and not cleaned.endswith((".", "!", "?")):
            cleaned = f"{cleaned}."
    # "keep" / "as_is" -> leave punctuation unchanged

    return cleaned

