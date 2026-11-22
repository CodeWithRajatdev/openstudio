"""Font discovery, ReportLab TTF registration, and text width measurement."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import reportlab
from PIL import ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_REPORTLAB_FONT_DIR = Path(os.path.dirname(reportlab.__file__)) / "fonts"
_BUNDLED_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

_VERA_FILES = {
    (False, False): "Vera.ttf",
    (True, False): "VeraBd.ttf",
    (False, True): "VeraIt.ttf",
    (True, True): "VeraBI.ttf",
}

_OPENSANS_FILES = {
    (False, False): "OpenSans-Regular.ttf",
    (True, False): "OpenSans-Bold.ttf",
    (False, True): "OpenSans-Italic.ttf",
    (True, True): "OpenSans-BoldItalic.ttf",
}

_VARIANT_SUFFIX_RE = re.compile(r"[-_](bold|italic|bolditalic|regular|bd|it|bi)$", re.IGNORECASE)


def _discover_custom_fonts(font_dir: str) -> dict[str, Path]:
    if not font_dir:
        return {}
    p = Path(font_dir)
    if not p.is_dir():
        return {}
    found: dict[str, Path] = {}
    for ttf in sorted(p.glob("*.ttf")):
        found[ttf.stem.lower()] = ttf
    return found


@lru_cache(maxsize=256)
def resolve_font_path(
    family: str = "Vera",
    bold: bool = False,
    italic: bool = False,
    font_dir: str = "",
) -> Path:
    """Resolve an embeddable TTF font path from bundled Open Sans, FONT_DIR, or Bitstream Vera."""
    fam_key = (family or "Vera").strip().lower()

    if fam_key in ("open sans", "opensans", "open-sans"):
        os_file = _BUNDLED_FONT_DIR / _OPENSANS_FILES[(bold, italic)]
        if os_file.is_file():
            return os_file
        reg = _BUNDLED_FONT_DIR / "OpenSans-Regular.ttf"
        if reg.is_file():
            return reg

    if fam_key not in ("vera", "bitstream vera", "bitstream vera sans") and font_dir:
        custom = _discover_custom_fonts(font_dir)
        candidates = []
        if bold and italic:
            candidates.extend([f"{fam_key}-bolditalic", f"{fam_key}bi", f"{fam_key}-bi"])
        elif bold:
            candidates.extend([f"{fam_key}-bold", f"{fam_key}bd", f"{fam_key}b"])
        elif italic:
            candidates.extend([f"{fam_key}-italic", f"{fam_key}it", f"{fam_key}i"])
        candidates.extend([f"{fam_key}-regular", fam_key])
        for cand in candidates:
            if cand in custom:
                return custom[cand]

    vera_name = _VERA_FILES[(bold, italic)]
    return _REPORTLAB_FONT_DIR / vera_name


def _is_embeddable_ttf(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        TTFont(f"_chk_{path.stem}", str(path))
        return True
    except Exception:
        return False


def list_available_fonts(font_dir: str = "") -> list[dict[str, str]]:
    """Return only fonts that have verified embeddable TTF files on disk."""
    fonts: list[dict[str, str]] = []
    seen_families: set[str] = set()

    os_reg = _BUNDLED_FONT_DIR / "OpenSans-Regular.ttf"
    if _is_embeddable_ttf(os_reg):
        fonts.append(
            {
                "family": "Open Sans",
                "label": "Open Sans (Embedded TTF)",
                "license": "SIL Open Font License 1.1",
            }
        )
        seen_families.add("open sans")

    vera_reg = _REPORTLAB_FONT_DIR / "Vera.ttf"
    if _is_embeddable_ttf(vera_reg):
        fonts.append(
            {
                "family": "Vera",
                "label": "Bitstream Vera Sans (Embedded TTF)",
                "license": "Bitstream Vera Fonts License",
            }
        )
        seen_families.add("vera")

    for stem_lower, ttf_path in _discover_custom_fonts(font_dir).items():
        if _VARIANT_SUFFIX_RE.search(stem_lower) and not stem_lower.endswith("-regular"):
            continue
        base_name = _VARIANT_SUFFIX_RE.sub("", ttf_path.stem)
        if base_name.lower() in seen_families:
            continue
        if _is_embeddable_ttf(ttf_path):
            fonts.append(
                {
                    "family": base_name,
                    "label": f"{base_name} (Custom TTF)",
                    "license": "Custom FONT_DIR",
                }
            )
            seen_families.add(base_name.lower())

    return fonts


def reportlab_font_name(
    family: str = "Vera",
    bold: bool = False,
    italic: bool = False,
    font_dir: str = "",
) -> str:
    """Register the resolved TTF with ReportLab if needed and return its registered name."""
    path = resolve_font_path(family=family, bold=bold, italic=italic, font_dir=font_dir)
    reg_name = f"WP_{path.stem}"
    if reg_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(reg_name, str(path)))
    return reg_name


@lru_cache(maxsize=64)
def _load_pil_font(path_str: str, size_int: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path_str, size=max(1, size_int))


def get_pil_font(
    font_size_px: float,
    family: str = "Vera",
    bold: bool = False,
    italic: bool = False,
    font_dir: str = "",
) -> ImageFont.FreeTypeFont:
    path = resolve_font_path(family=family, bold=bold, italic=italic, font_dir=font_dir)
    return _load_pil_font(str(path), max(1, int(round(font_size_px))))


def measure_text_width(
    text: str,
    font_size_pt: float,
    family: str = "Vera",
    bold: bool = False,
    italic: bool = False,
    font_dir: str = "",
) -> float:
    """Measure text width in points using the registered TTF font."""
    reg_name = reportlab_font_name(family=family, bold=bold, italic=italic, font_dir=font_dir)
    return float(pdfmetrics.stringWidth(text, reg_name, font_size_pt))
