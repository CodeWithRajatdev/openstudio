"""SVG, PDF (ReportLab), and PNG (Pillow) renderers consuming PagePrimitives."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from .fonts import get_pil_font, reportlab_font_name
from .primitives import LinePrimitive, PagePrimitives, RectPrimitive, TextPrimitive


def render_svg(page: PagePrimitives) -> str:
    """Render a single PagePrimitives into pure vector SVG (<rect>, <line>, <text> only)."""
    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": f"{page.width_pt:.2f}pt",
            "height": f"{page.height_pt:.2f}pt",
            "viewBox": f"0 0 {page.width_pt:.2f} {page.height_pt:.2f}",
        },
    )

    for prim in page.primitives:
        if isinstance(prim, RectPrimitive):
            attrs = {
                "x": f"{prim.x:.2f}",
                "y": f"{prim.y:.2f}",
                "width": f"{prim.width:.2f}",
                "height": f"{prim.height:.2f}",
                "fill": prim.fill if prim.fill else "none",
            }
            if prim.stroke and prim.stroke_width > 0:
                attrs["stroke"] = prim.stroke
                attrs["stroke-width"] = f"{prim.stroke_width:.2f}"
            else:
                attrs["stroke"] = "none"
            ET.SubElement(svg, "rect", attrs)
        elif isinstance(prim, LinePrimitive):
            ET.SubElement(
                svg,
                "line",
                {
                    "x1": f"{prim.x1:.2f}",
                    "y1": f"{prim.y1:.2f}",
                    "x2": f"{prim.x2:.2f}",
                    "y2": f"{prim.y2:.2f}",
                    "stroke": prim.stroke,
                    "stroke-width": f"{prim.stroke_width:.2f}",
                    "stroke-linecap": "square",
                },
            )
        elif isinstance(prim, TextPrimitive):
            attrs = {
                "x": f"{prim.x:.2f}",
                "y": f"{prim.y:.2f}",
                "font-family": prim.font_family,
                "font-size": f"{prim.font_size:.2f}",
                "fill": prim.color,
                "text-anchor": prim.anchor,
            }
            if prim.bold:
                attrs["font-weight"] = "bold"
            if prim.italic:
                attrs["font-style"] = "italic"
            el = ET.SubElement(svg, "text", attrs)
            el.text = prim.text

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(svg, encoding="unicode")


def render_svgs(pages: list[PagePrimitives]) -> list[str]:
    return [render_svg(p) for p in pages]


def render_pdf(pages: list[PagePrimitives], font_dir: str = "") -> bytes:
    """Render one or more PagePrimitives into a multi-page PDF with embedded TTF fonts."""
    if not pages:
        raise ValueError("Cannot render PDF with 0 pages")

    first_text = next(
        (prim for p in pages for prim in p.primitives if isinstance(prim, TextPrimitive)),
        None,
    )
    initial_font = reportlab_font_name(
        family=first_text.font_family if first_text else "Open Sans",
        bold=first_text.bold if first_text else False,
        italic=first_text.italic if first_text else False,
        font_dir=font_dir,
    )

    buf = io.BytesIO()
    first = pages[0]
    c = canvas.Canvas(
        buf,
        pagesize=(first.width_pt, first.height_pt),
        initialFontName=initial_font,
        initialFontSize=10.0,
    )

    for idx, page in enumerate(pages):
        if idx > 0:
            c.showPage()
            c.setPageSize((page.width_pt, page.height_pt))

        if page.bookmark:
            bm_key = f"bm_{idx}"
            c.bookmarkPage(bm_key)
            c.addOutlineEntry(page.bookmark, bm_key, level=0, closed=False)

        h = page.height_pt
        for prim in page.primitives:
            if isinstance(prim, RectPrimitive):
                has_fill = bool(prim.fill)
                has_stroke = bool(prim.stroke and prim.stroke_width > 0)
                if has_fill:
                    c.setFillColor(HexColor(prim.fill))
                if has_stroke:
                    c.setStrokeColor(HexColor(prim.stroke))
                    c.setLineWidth(prim.stroke_width)
                c.rect(
                    prim.x,
                    h - prim.y - prim.height,
                    prim.width,
                    prim.height,
                    stroke=1 if has_stroke else 0,
                    fill=1 if has_fill else 0,
                )
            elif isinstance(prim, LinePrimitive):
                c.setStrokeColor(HexColor(prim.stroke))
                c.setLineWidth(prim.stroke_width)
                c.line(prim.x1, h - prim.y1, prim.x2, h - prim.y2)
            elif isinstance(prim, TextPrimitive):
                font_name = reportlab_font_name(
                    family=prim.font_family,
                    bold=prim.bold,
                    italic=prim.italic,
                    font_dir=font_dir,
                )
                c.setFont(font_name, prim.font_size)
                c.setFillColor(HexColor(prim.color))
                pdf_y = h - prim.y
                if prim.anchor == "middle":
                    c.drawCentredString(prim.x, pdf_y, prim.text)
                elif prim.anchor == "end":
                    c.drawRightString(prim.x, pdf_y, prim.text)
                else:
                    c.drawString(prim.x, pdf_y, prim.text)

    c.save()
    return buf.getvalue()


def render_png(page: PagePrimitives, dpi: int = 300, font_dir: str = "") -> bytes:
    """Render a single PagePrimitives into a PNG image at the requested DPI."""
    scale = dpi / 72.0
    px_w = max(1, int(round(page.width_pt * scale)))
    px_h = max(1, int(round(page.height_pt * scale)))

    img = Image.new("RGB", (px_w, px_h), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    for prim in page.primitives:
        if isinstance(prim, RectPrimitive):
            x0 = prim.x * scale
            y0 = prim.y * scale
            x1 = (prim.x + prim.width) * scale
            y1 = (prim.y + prim.height) * scale
            outline = prim.stroke if (prim.stroke and prim.stroke_width > 0) else None
            width_px = max(1, int(round(prim.stroke_width * scale))) if outline else 0
            draw.rectangle([x0, y0, x1, y1], fill=prim.fill, outline=outline, width=width_px)
        elif isinstance(prim, LinePrimitive):
            width_px = max(1, int(round(prim.stroke_width * scale)))
            draw.line(
                [(prim.x1 * scale, prim.y1 * scale), (prim.x2 * scale, prim.y2 * scale)],
                fill=prim.stroke,
                width=width_px,
            )
        elif isinstance(prim, TextPrimitive):
            font = get_pil_font(
                prim.font_size * scale,
                family=prim.font_family,
                bold=prim.bold,
                italic=prim.italic,
                font_dir=font_dir,
            )
            anchor_map = {"start": "ls", "middle": "ms", "end": "rs"}
            draw.text(
                (prim.x * scale, prim.y * scale),
                prim.text,
                fill=prim.color,
                font=font,
                anchor=anchor_map.get(prim.anchor, "ls"),
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(dpi, dpi))
    return buf.getvalue()


def render_pngs(pages: list[PagePrimitives], dpi: int = 300, font_dir: str = "") -> list[bytes]:
    return [render_png(p, dpi=dpi, font_dir=font_dir) for p in pages]
