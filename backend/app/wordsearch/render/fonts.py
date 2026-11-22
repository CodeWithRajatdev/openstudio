"""Font catalogue shared by the SVG renderer, text measurement and PDF export.

Every family the UI offers is listed here once. For each family we know:
  * the CSS fallback stack written into the SVG (browsers / design tools),
  * any bundled TrueType files in `app/fonts` (such as Open Sans),
  * the standard PDF font used when no bundled TrueType file is present.

Bundled TTFs are registered with ReportLab/svglib and EMBEDDED in the PDF, so
Open Sans in the PDF matches the browser preview. Standard families (Arial,
Helvetica, Georgia, Times New Roman, Courier New, etc.) are registered in
svglib's font map against the 14 standard PDF fonts for instant vector export.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

BUNDLED_DIR = Path(__file__).resolve().parents[1] / "fonts"

STYLES = ("regular", "bold", "italic", "bold_italic")


@dataclass(frozen=True)
class FontFamily:
    name: str
    stack: str                       # CSS font-family list (after the family itself)
    files: dict                      # style -> list of candidate file names
    pdf_fallback: str                # "Helvetica" | "Times-Roman" | "Courier"


def _f(regular, bold=None, italic=None, bold_italic=None):
    return {"regular": regular, "bold": bold or [], "italic": italic or [],
            "bold_italic": bold_italic or []}


CATALOG: dict[str, FontFamily] = {f.name: f for f in [
    FontFamily("Open Sans", "Arial, Helvetica, sans-serif",
               _f(["OpenSans-Regular.ttf"], ["OpenSans-Bold.ttf"], ["OpenSans-Italic.ttf"],
                  ["OpenSans-BoldItalic.ttf"]), "Helvetica"),
    # System fonts with full 4-style TrueType coverage (Regular, Bold, Italic, Bold Italic).
    FontFamily("Arial", "Helvetica, sans-serif",
               _f(["arial.ttf"], ["arialbd.ttf", "Arial Bold.ttf"],
                  ["ariali.ttf", "Arial Italic.ttf"], ["arialbi.ttf", "Arial Bold Italic.ttf"]),
               "Helvetica"),
    FontFamily("Verdana", "Geneva, sans-serif",
               _f(["verdana.ttf"], ["verdanab.ttf", "Verdana Bold.ttf"],
                  ["verdanai.ttf", "Verdana Italic.ttf"],
                  ["verdanaz.ttf", "Verdana Bold Italic.ttf"]), "Helvetica"),
    FontFamily("Trebuchet MS", "Helvetica, sans-serif",
               _f(["trebuc.ttf", "Trebuchet MS.ttf"], ["trebucbd.ttf", "Trebuchet MS Bold.ttf"],
                  ["trebucit.ttf", "Trebuchet MS Italic.ttf"], ["trebucbi.ttf"]), "Helvetica"),
    FontFamily("Comic Sans MS", "cursive",
               _f(["comic.ttf", "Comic Sans MS.ttf"], ["comicbd.ttf", "Comic Sans MS Bold.ttf"],
                  ["comici.ttf"], ["comicz.ttf"]), "Helvetica"),
    FontFamily("Georgia", "'Times New Roman', serif",
               _f(["georgia.ttf"], ["georgiab.ttf", "Georgia Bold.ttf"],
                  ["georgiai.ttf", "Georgia Italic.ttf"],
                  ["georgiaz.ttf", "Georgia Bold Italic.ttf"]), "Times-Roman"),
    FontFamily("Times New Roman", "Times, serif",
               _f(["times.ttf", "Times New Roman.ttf"], ["timesbd.ttf", "Times New Roman Bold.ttf"],
                  ["timesi.ttf", "Times New Roman Italic.ttf"],
                  ["timesbi.ttf", "Times New Roman Bold Italic.ttf"]), "Times-Roman"),
    FontFamily("Courier New", "Courier, monospace",
               _f(["cour.ttf", "Courier New.ttf"], ["courbd.ttf", "Courier New Bold.ttf"],
                  ["couri.ttf", "Courier New Italic.ttf"],
                  ["courbi.ttf", "Courier New Bold Italic.ttf"]), "Courier"),
]}

# Old projects stored full CSS stacks or unembeddable system fonts; map them to embeddable families.
LEGACY = {
    "arial, helvetica, sans-serif": "Arial",
    "georgia, 'times new roman', serif": "Georgia",
    "'courier new', courier, monospace": "Courier New",
    "helvetica": "Arial",
    "tahoma": "Verdana",
}

_STD_VARIANTS = {
    "Helvetica": {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique",
                  "bold_italic": "Helvetica-BoldOblique"},
    "Times-Roman": {"regular": "Times-Roman", "bold": "Times-Bold", "italic": "Times-Italic",
                    "bold_italic": "Times-BoldItalic"},
    "Courier": {"regular": "Courier", "bold": "Courier-Bold", "italic": "Courier-Oblique",
                "bold_italic": "Courier-BoldOblique"},
}


def style_key(weight: str = "normal", style: str = "normal") -> str:
    bold = str(weight).lower() in ("bold", "700", "800", "900")
    italic = str(style).lower() in ("italic", "oblique")
    return {(False, False): "regular", (True, False): "bold",
            (False, True): "italic", (True, True): "bold_italic"}[(bold, italic)]


def family_of(value: str) -> Optional[FontFamily]:
    """Catalogue entry for a stored font value (family name or legacy CSS stack)."""
    if not value:
        return None
    v = value.strip()
    if v in CATALOG:
        return CATALOG[v]
    legacy = LEGACY.get(v.lower())
    if legacy:
        return CATALOG[legacy]
    first = v.split(",")[0].strip().strip("'\"")
    return CATALOG.get(first)


def css_stack(value: str) -> str:
    """font-family attribute value for the SVG."""
    fam = family_of(value)
    if fam is None:
        return value                     # custom CSS stack, written as given
    name = f"'{fam.name}'" if " " in fam.name else fam.name
    return f"{name}, {fam.stack}"


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    dirs += [Path("/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
             Path.home() / "Library" / "Fonts"]
    return dirs


def _font_dirs() -> list[Path]:
    dirs = [BUNDLED_DIR]
    extra = os.environ.get("WOODPECKER_FONT_DIRS")
    if extra:
        dirs += [Path(p) for p in extra.split(os.pathsep) if p]
    if os.environ.get("WOODPECKER_SYSTEM_FONTS", "1") != "0":
        dirs += _system_font_dirs()
    out: list[Path] = []
    for d in dirs:
        try:
            if str(d) and d.exists():
                out.append(d)
        except OSError:
            continue
    return out


@lru_cache(maxsize=None)
def _index() -> dict[str, str]:
    """lower-case file name -> absolute path, searched once."""
    found: dict[str, str] = {}
    for d in _font_dirs():
        try:
            for root, _, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(".ttf"):
                        found.setdefault(fn.lower(), os.path.join(root, fn))
        except OSError:
            continue
    return found


@lru_cache(maxsize=None)
def font_file(family: str, key: str) -> Optional[str]:
    """Path of the TTF for this family/style, or None."""
    fam = CATALOG.get(family)
    if fam is None:
        return None
    for cand in fam.files.get(key, []):
        p = _index().get(cand.lower())
        if p:
            return p
    return None


def pdf_font_name(value: str, weight="normal", style="normal") -> tuple[str, bool]:
    """(ReportLab font name, embedded?) used for this text in the PDF."""
    fam = family_of(value)
    key = style_key(weight, style)
    if fam is not None:
        path = font_file(fam.name, key)
        if path:
            reg = _register_ttf(fam.name, key, path)
            if reg:
                return reg, True
        return _STD_VARIANTS[fam.pdf_fallback][key], False
    return _STD_VARIANTS["Helvetica"][key], False


@lru_cache(maxsize=None)
def _register_ttf(family: str, key: str, path: str) -> Optional[str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    name = f"WP-{family.replace(' ', '')}-{key}"
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        return name
    except Exception:
        return None


@lru_cache(maxsize=None)
def _register_svglib_variant(fam_name: str, key: str) -> dict:
    from svglib.fonts import register_font
    w = "bold" if key in ("bold", "bold_italic") else "normal"
    s = "italic" if key in ("italic", "bold_italic") else "normal"
    rl_name, embedded = pdf_font_name(fam_name, w, s)
    if embedded:
        register_font(fam_name, font_file(fam_name, key), weight=w, style=s, rlgFontName=rl_name)
    else:
        register_font(fam_name, weight=w, style=s, rlgFontName=rl_name)
    return {"family": fam_name, "style": key, "pdf_font": rl_name, "embedded": embedded}


def register_for_svglib(values: list[tuple[str, str, str]]) -> list[dict]:
    """Make svglib map each (family, weight, style) used on the pages to its
    TrueType font (embedded) or fallback. Also configures ReportLab's base
    canvas/graphics font to bundled Open Sans so no unembedded Helvetica
    resource is ever emitted. Returns a report."""
    from reportlab import rl_config
    from reportlab.graphics.shapes import STATE_DEFAULTS

    base_rl, base_emb = pdf_font_name("Open Sans", "normal", "normal")
    if base_emb:
        rl_config.canvas_basefontname = base_rl
        rl_config.defaultGraphicsFontName = base_rl
        STATE_DEFAULTS["fontName"] = base_rl

    report = []
    seen = set()
    fams = set()
    for value, weight, style in values:
        fam = family_of(value)
        key = style_key(weight, style)
        if fam is None:
            continue
        if fam.name not in fams:
            fams.add(fam.name)
            for k in STYLES:
                _register_svglib_variant(fam.name, k)
        if (fam.name, key) not in seen:
            seen.add((fam.name, key))
            report.append(_register_svglib_variant(fam.name, key))
    return report


def text_width(text: str, value: str, size: float, weight="normal", style="normal") -> float:
    """Width of `text` at font `size` (same unit as size) using real font metrics."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    name, _ = pdf_font_name(value, weight, style)
    try:
        return stringWidth(text, name, size)
    except Exception:                    # pragma: no cover - metrics unavailable
        return len(text) * size * 0.6


def not_embeddable(values: list[tuple[str, str, str]]) -> list[str]:
    """Human-readable list of (family, weight, style) uses that cannot be embedded."""
    out = []
    for value, weight, style in values:
        fam = family_of(value)
        key = style_key(weight, style)
        if fam is None or font_file(fam.name, key) is None:
            label = f"{fam.name if fam else value} {key.replace('_', ' ').title()}"
            if label not in out:
                out.append(label)
    return out


def available() -> list[dict]:
    """For the UI: which families exist and whether the PDF can embed them."""
    out = []
    for fam in CATALOG.values():
        styles = {k: font_file(fam.name, k) is not None for k in STYLES}
        out.append({"family": fam.name, "css": css_stack(fam.name), "embedded_styles": styles,
                    "pdf_fallback": fam.pdf_fallback,
                    "bundled": any(str(font_file(fam.name, k) or "").startswith(str(BUNDLED_DIR))
                                   for k in STYLES)})
    return out
