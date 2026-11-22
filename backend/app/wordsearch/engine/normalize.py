"""Word normalisation. Never discards a word silently: raises instead."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizeRules:
    remove_spaces: bool = True        # "ICE CREAM" -> "ICECREAM"
    remove_hyphens: bool = True       # "WELL-KNOWN" -> "WELLKNOWN"
    remove_apostrophes: bool = True   # "DON'T" -> "DONT"
    strip_accents: bool = True        # "CAFÉ" -> "CAFE"
    allow_digits: bool = False


class InvalidWordError(ValueError):
    pass


def normalize_word(original: str, rules: NormalizeRules | None = None) -> str:
    rules = rules or NormalizeRules()
    s = original.strip()
    if rules.strip_accents:
        s = "".join(
            c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
        )
    s = s.upper()
    if rules.remove_spaces:
        s = re.sub(r"\s+", "", s)
    if rules.remove_hyphens:
        s = re.sub(r"[-\u2010-\u2015]", "", s)
    if rules.remove_apostrophes:
        s = re.sub(r"['\u2019\u2018`]", "", s)
    pattern = r"[A-Z0-9]+" if rules.allow_digits else r"[A-Z]+"
    if not s or not re.fullmatch(pattern, s):
        raise InvalidWordError(
            f"Word {original!r} has no valid grid form after normalisation "
            f"(got {s!r}); only letters{' and digits' if rules.allow_digits else ''} can be placed."
        )
    return s
