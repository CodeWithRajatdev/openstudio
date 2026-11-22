"""Vector PDF book export via svglib + ReportLab.

svglib parses our SVG into a ReportLab `Drawing` of paths, rectangles, ellipses
and text objects; `renderPDF.draw` emits native PDF vector and text operators
onto a Canvas sized to the exact trim dimensions. No rasterisation happens
anywhere in this pipeline.

Every page is produced by `app.render.book.render_book`, the same function that
drives the live preview, so page size, margins (including KDP inside/outside
gutter margins), titles, clues, solutions, page numbers and page order match
the preview page-for-page.

After building, `verify_pdf` automatically checks that:
  * zero raster images exist in the PDF,
  * vector drawing operators are present,
  * page count equals the book plan (`page_plan`),
  * trim size matches the layout dimensions,
  * every font resource in the PDF is embedded (`emb = yes`),
  * no transparency tricks (`/SMask`, fractional `/ca` or `/CA`) are used.
"""
from __future__ import annotations

import io
import re
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Optional, Sequence, Union

from reportlab.graphics import renderPDF
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from app.wordsearch.engine.bulk import BulkResult
from app.wordsearch.importers.models import chapter_label
from app.wordsearch.render import PageLayout, book_pages, layout_fonts, page_plan, render_book_page, resolve_title
from app.wordsearch.render.fonts import not_embeddable, register_for_svglib

DEFAULT_PDF_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "pdf_exports"
PdfSource = Union[bytes, str, Path]


@contextmanager
def _open_pdf_stream(pdf_source: PdfSource) -> Iterator[BinaryIO]:
    if isinstance(pdf_source, (str, Path)):
        import mmap
        with open(pdf_source, "rb") as fh:
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm_buf:
                yield mm_buf  # type: ignore[misc]
    else:
        yield io.BytesIO(pdf_source)


def _file_contains_token(path: Path, tokens: tuple[bytes, ...], chunk_size: int = 1024 * 1024) -> bool:
    overlap = max(len(t) for t in tokens)
    tail = b""
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            window = tail + chunk
            if any(t in window for t in tokens):
                return True
            tail = window[-overlap:]
    return False


def slugify(text: str, fallback: str = "book") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or fallback


def pdf_filename(project_name: str, fallback: str = "book") -> str:
    raw = (project_name or "").strip()
    if raw.lower().endswith(".pdf"):
        raw = raw[:-4].strip()
    return f"{slugify(raw, fallback)}.pdf"


@dataclass
class PdfOptions:
    per_page_answers: int = 4          # 1, 2, 4, 6 or 9 answer keys per page
    answer_style: str = "rounded_rect"
    page_numbers: Optional[bool] = None    # None = follow layout.page_numbers
    include_answers: bool = True
    title: str = "Word Search Book"
    author: str = "Woodpecker"


def _draw_svg_page(c: canvas.Canvas, svg: str, page_h_pt: float) -> None:
    drawing = svg2rlg(io.BytesIO(svg.encode("utf-8")))
    if drawing is None:
        raise RuntimeError("svglib failed to parse generated SVG")
    # svg uses mm coordinates in viewBox (width="<W>mm" height="<H>mm" viewBox="0 0 W H").
    # svglib converts width/height in mm to points, and sets a top-level scale;
    # draw at (0, 0) filling the page.
    renderPDF.draw(drawing, c, 0, 0)
    c.showPage()


def build_pdf(puzzles: Sequence[tuple], layout: Optional[PageLayout] = None,
              options: Optional[PdfOptions] = None,
              progress: Optional[Callable[[int, int], None]] = None,
              output_path: Optional[Union[str, Path]] = None,
              return_bytes: bool = True) -> tuple[bytes, dict]:
    """Build a complete interior PDF (puzzles in chapter order, then solutions,
    plus a trailing blank page when the total would be odd).

    Streams rendered page binaries directly to a local disk cache file one page
    at a time so the full SVG list and compiled PDF do not accumulate in RAM.
    Automatically verifies vector operators, zero raster images, embedded fonts,
    trim size, and exact page count before returning.

    puzzles: sequence of (Puzzle, chapter_title[, clue_words]) in chapter order.
    Returns (pdf_bytes, manifest_dict).
    """
    if not puzzles:
        raise ValueError("cannot build a PDF with zero puzzles")
    layout = layout or PageLayout()
    options = options or PdfOptions()
    if options.page_numbers is not None:
        layout = layout.with_(page_numbers=options.page_numbers)

    items = [(it[0], it[1], i, *it[2:]) for i, it in enumerate(puzzles)]
    fonts_used = layout_fonts(layout, options.include_answers, options.per_page_answers)
    missing_fonts = not_embeddable(fonts_used)
    if missing_fonts:
        raise ValueError(
            "Cannot build PDF because the following font styles cannot be embedded: "
            + ", ".join(missing_fonts)
        )
    font_report = register_for_svglib(fonts_used)
    if any(not f.get("embedded") for f in font_report):
        unemb = [f"{f['family']} ({f['style']})" for f in font_report if not f.get("embedded")]
        raise ValueError(f"Cannot build PDF with unembedded font(s): {', '.join(unemb)}")

    if output_path is not None:
        cache_path = Path(output_path)
    else:
        cache_path = DEFAULT_PDF_CACHE_DIR / f"{slugify(options.title)}-{uuid.uuid4().hex[:12]}.pdf"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    w_pt, h_pt = layout.page_width * mm, layout.page_height * mm
    page_descriptors = book_pages(
        len(items),
        layout.puzzles_per_page,
        options.per_page_answers,
        options.include_answers,
    )
    total_steps = len(page_descriptors)
    done = 0
    answers_Bookmark_done = False

    c = canvas.Canvas(str(cache_path), pagesize=(w_pt, h_pt), pageCompression=1)
    c.setTitle(options.title)
    c.setAuthor(options.author)
    c.setSubject("Word search puzzle book (vector)")

    for page in page_descriptors:
        if page.kind == "puzzle":
            for pos in page.positions:
                t = items[pos][1]
                bm = (resolve_title(layout.with_(title_enabled=True), t, pos)
                      or t or f"Puzzle {pos + 1}")
                key = f"p{pos}"
                c.bookmarkPage(key)
                c.addOutlineEntry(bm, key, level=0)
            chunk = [items[pos] for pos in page.positions]
            svg = render_book_page(
                page.kind, chunk, layout, page.number, total_steps,
                options.per_page_answers, options.answer_style,
            )
            _draw_svg_page(c, svg, h_pt)
        elif page.kind == "solution":
            if not answers_Bookmark_done:
                c.bookmarkPage("answers")
                c.addOutlineEntry("Solutions", "answers", level=0)
                answers_Bookmark_done = True
            chunk = [items[pos] for pos in page.positions]
            svg = render_book_page(
                page.kind, chunk, layout, page.number, total_steps,
                options.per_page_answers, options.answer_style,
            )
            _draw_svg_page(c, svg, h_pt)
        else:  # trailing blank page so the book has an even page count
            c.showPage()
        done += 1
        if progress:
            progress(done, total_steps)

    c.save()

    plan = page_plan(len(items), layout.puzzles_per_page, options.per_page_answers,
                     include_solutions=options.include_answers)
    verification = verify_pdf(
        cache_path,
        expected_pages=plan["total_pages"],
        expected_width_mm=layout.page_width,
        expected_height_mm=layout.page_height,
    )
    byte_size = cache_path.stat().st_size
    info = {
        "puzzle_pages": plan["puzzle_pages"],
        "answer_pages": plan["solution_pages"],
        "blank_pages": plan["blank_pages"],
        "total_pages": plan["total_pages"],
        "answers_start_page": (plan["puzzle_pages"] + 1) if plan["solution_pages"] else None,
        "page_size_mm": [layout.page_width, layout.page_height],
        "bytes": byte_size,
        "cache_path": str(cache_path),
        "fonts": font_report,
        "pdf_fonts": verification["pdf_fonts"],
        "vector_check": verification,
    }
    data = cache_path.read_bytes() if return_bytes else b""
    return data, info


def build_book_pdf(project_name: str, result: BulkResult,
                   layout: Optional[PageLayout] = None,
                   options: Optional[PdfOptions] = None,
                   output_path: Optional[Union[str, Path]] = None,
                   return_bytes: bool = True) -> tuple[bytes, dict]:
    """Build the single vector PDF for a finished bulk generation result.

    Streams page binaries directly to a local disk cache (`output_path` or
    `DEFAULT_PDF_CACHE_DIR`). Enforces Requirement 5 (no partial books): if any
    chapter failed or if there are no chapters, raises ValueError with a
    plain-language message per failed chapter.
    """
    if not result.chapters:
        raise ValueError("No chapters to export.")
    if result.failed:
        msgs = [f"{chapter_label(c.index, c.title)} failed: {c.error}" for c in result.failed]
        raise ValueError("Cannot export a partial book. " + " ".join(msgs))
    opts = options or PdfOptions(title=project_name or "Word Search Book")
    if not opts.title:
        opts.title = project_name or "Word Search Book"
    puzzles = [(c.puzzle, c.title, c.words) for c in result.succeeded]
    return build_pdf(
        puzzles,
        layout=layout,
        options=opts,
        output_path=output_path,
        return_bytes=return_bytes,
    )


def _collect_fonts_from_reader(reader) -> list[dict]:
    seen: dict[str, dict] = {}
    for page in reader.pages:
        res = page.get("/Resources") or {}
        if hasattr(res, "get_object"):
            res = res.get_object()
        fonts = res.get("/Font") or {}
        if hasattr(fonts, "get_object"):
            fonts = fonts.get_object()
        for _, fref in fonts.items():
            fobj = fref.get_object() if hasattr(fref, "get_object") else fref
            base_font = str(fobj.get("/BaseFont", "")).lstrip("/")
            subtype = str(fobj.get("/Subtype", "")).lstrip("/")
            has_uni = "/ToUnicode" in fobj
            desc = fobj.get("/FontDescriptor")
            if desc is None and "/DescendantFonts" in fobj:
                df_list = fobj["/DescendantFonts"]
                if hasattr(df_list, "get_object"):
                    df_list = df_list.get_object()
                if df_list:
                    df0 = df_list[0].get_object() if hasattr(df_list[0], "get_object") else df_list[0]
                    desc = df0.get("/FontDescriptor")
                    subtype = str(df0.get("/Subtype", subtype)).lstrip("/")
            if desc is not None and hasattr(desc, "get_object"):
                desc = desc.get_object()
            emb = bool(desc and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")))
            sub = bool(re.match(r"^[A-Z]{6}\+", base_font))
            key = f"{base_font}|{subtype}|{emb}"
            if key not in seen:
                seen[key] = {
                    "name": base_font,
                    "type": subtype,
                    "emb": emb,
                    "sub": sub,
                    "uni": has_uni,
                }
    return list(seen.values())


def inspect_pdf_fonts(pdf_source: PdfSource) -> list[dict]:
    """Inspect all font dictionaries across every page in `pdf_source` (equivalent to `pdffonts`).

    Returns a list of unique font entries:
      {"name": str, "type": str, "emb": bool, "sub": bool, "uni": bool}
    """
    import pypdf

    with _open_pdf_stream(pdf_source) as stream:
        reader = pypdf.PdfReader(stream)
        return _collect_fonts_from_reader(reader)


def inspect_pdf_vectors(pdf_source: PdfSource) -> dict:
    """Verify that `pdf_source` contains vector drawing operators and zero raster images."""
    import pypdf

    with _open_pdf_stream(pdf_source) as stream:
        reader = pypdf.PdfReader(stream)
        images = 0
        vector_ops = 0
        for page in reader.pages:
            res = page.get("/Resources") or {}
            xobj = res.get("/XObject") if hasattr(res, "get") else None
            if xobj:
                for obj in xobj.values():
                    o = obj.get_object()
                    if o.get("/Subtype") == "/Image":
                        images += 1
            data = page.get_contents()
            raw = data.get_data() if data is not None else b""
            # Count basic PDF path operators: m (moveto), l (lineto), re (rect), S/s/f/B (stroke/fill).
            vector_ops += len(re.findall(rb"(?<![A-Za-z])(?:m|l|c|re|S|f|B)(?![A-Za-z])", raw))
            if re.search(rb"(?<![A-Za-z])BI(?![A-Za-z])", raw):
                images += 1
        num_pages = len(reader.pages)
        pdf_fonts = _collect_fonts_from_reader(reader)
    return {
        "pages": num_pages,
        "images": images,
        "vector_ops": vector_ops,
        "pdf_fonts": pdf_fonts,
    }


def verify_pdf(pdf_source: PdfSource, expected_pages: Optional[int] = None,
               expected_width_mm: Optional[float] = None,
               expected_height_mm: Optional[float] = None) -> dict:
    """Strictly verify a generated PDF for vector purity, page count, trim size,
    embedded fonts, and absence of transparency tricks. Raises ValueError on any failure."""
    if isinstance(pdf_source, (str, Path)):
        path = Path(pdf_source)
        if not path.exists() or path.stat().st_size < 5:
            raise ValueError("PDF verification failed: output is not a valid PDF header.")
        with open(path, "rb") as fh:
            header = fh.read(5)
        if header != b"%PDF-":
            raise ValueError("PDF verification failed: output is not a valid PDF header.")
        if _file_contains_token(path, (b"/Subtype /Image", b"/DCTDecode")):
            raise ValueError("PDF verification failed: raster image stream detected in PDF.")
    else:
        if not pdf_source or not pdf_source.startswith(b"%PDF-"):
            raise ValueError("PDF verification failed: output is not a valid PDF header.")
        if b"/Subtype /Image" in pdf_source or b"/DCTDecode" in pdf_source:
            raise ValueError("PDF verification failed: raster image stream detected in PDF.")

    vec = inspect_pdf_vectors(pdf_source)
    if vec["images"] != 0:
        raise ValueError(f"PDF verification failed: expected 0 embedded images, found {vec['images']}.")
    if vec["vector_ops"] <= 0:
        raise ValueError("PDF verification failed: no vector drawing operators found in PDF.")
    if expected_pages is not None and vec["pages"] != expected_pages:
        raise ValueError(
            f"PDF verification failed: page count is {vec['pages']}, expected {expected_pages}."
        )

    pdf_fonts = vec["pdf_fonts"]
    if not pdf_fonts:
        raise ValueError("PDF verification failed: no font resources found in PDF.")
    unembedded = [f["name"] for f in pdf_fonts if not f["emb"]]
    if unembedded:
        raise ValueError(
            f"PDF verification failed: unembedded font(s) in PDF: {', '.join(unembedded)}"
        )

    import pypdf
    with _open_pdf_stream(pdf_source) as stream:
        reader = pypdf.PdfReader(stream)
        if expected_width_mm is not None and expected_height_mm is not None:
            exp_w_pt = expected_width_mm / 25.4 * 72.0
            exp_h_pt = expected_height_mm / 25.4 * 72.0
            for idx, page in enumerate(reader.pages):
                box = page.mediabox
                if abs(float(box.width) - exp_w_pt) > 0.5 or abs(float(box.height) - exp_h_pt) > 0.5:
                    raise ValueError(
                        f"PDF verification failed: page {idx + 1} trim size "
                        f"({float(box.width):.1f}x{float(box.height):.1f} pt) does not match "
                        f"expected ({exp_w_pt:.1f}x{exp_h_pt:.1f} pt)."
                    )
                res = page.get("/Resources") or {}
                if hasattr(res, "get_object"):
                    res = res.get_object()
                extg = res.get("/ExtGState")
                if extg:
                    if hasattr(extg, "get_object"):
                        extg = extg.get_object()
                    for gval in extg.values():
                        g = gval.get_object() if hasattr(gval, "get_object") else gval
                        ca = float(g.get("/ca", 1.0))
                        CA = float(g.get("/CA", 1.0))
                        smask = g.get("/SMask")
                        if ca < 1.0 or CA < 1.0 or (smask is not None and str(smask) != "/None"):
                            raise ValueError(
                                f"PDF verification failed: transparency state found on page {idx + 1}."
                            )

    return vec
