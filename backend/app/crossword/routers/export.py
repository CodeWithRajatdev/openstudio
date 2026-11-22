"""Export rendering endpoint (SVG, PDF, PNG)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from ..config import get_settings
from ..schemas import StatelessExportIn
from ..services.export.fonts import list_available_fonts, resolve_font_path
from ..services.export.geometry import ExportEntry, ExportPuzzleData, build_export_pages
from ..services.export.renderers import render_pdf, render_png, render_svg
from ..services.export.settings import ExportSettings

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/fonts")
def get_embeddable_fonts():
    return list_available_fonts(font_dir=get_settings().font_dir)


@router.get("/fonts/file")
def get_font_file(
    family: str = Query("Open Sans"),
    bold: bool = Query(False),
    italic: bool = Query(False),
):
    path = resolve_font_path(
        family=family,
        bold=bold,
        italic=italic,
        font_dir=get_settings().font_dir,
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Font file not found")
    return FileResponse(
        path,
        media_type="font/ttf",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/fonts.css")
def get_fonts_css():
    """Serve @font-face rules for all embeddable fonts so inline SVG previews match PDF output."""
    fonts = list_available_fonts(font_dir=get_settings().font_dir)
    rules: list[str] = []
    variants = [
        (False, False, "400", "normal"),
        (True, False, "700", "normal"),
        (False, True, "400", "italic"),
        (True, True, "700", "italic"),
    ]
    for f in fonts:
        fam = f["family"]
        q_fam = quote(fam)
        escaped_fam = fam.replace("\\", "\\\\").replace("'", "\\'")
        for bold, italic, weight, style in variants:
            url = f"/api/export/fonts/file?family={q_fam}&bold={str(bold).lower()}&italic={str(italic).lower()}"
            rules.append(
                f"@font-face {{\n"
                f"  font-family: '{escaped_fam}';\n"
                f"  src: url('{url}') format('truetype');\n"
                f"  font-weight: {weight};\n"
                f"  font-style: {style};\n"
                f"  font-display: swap;\n"
                f"}}"
            )
    return Response(
        content="\n".join(rules),
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/render")
def render_stateless_export(body: StatelessExportIn):
    settings = ExportSettings(**body.settings.model_dump())
    font_dir = get_settings().font_dir
    puzzle = ExportPuzzleData(
        title=body.title,
        rows=body.rows,
        cols=body.cols,
        grid=body.grid,
        entries=[ExportEntry(**e.model_dump()) for e in body.entries],
    )
    try:
        pages = build_export_pages(puzzle, body.kind, settings, font_dir=font_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.format == "pdf":
        pdf_bytes = render_pdf(pages, font_dir=font_dir)
        return Response(content=pdf_bytes, media_type="application/pdf")

    if body.page >= len(pages):
        raise HTTPException(status_code=400, detail=f"Page {body.page} out of range (total {len(pages)})")

    if body.format == "svg":
        svg_str = render_svg(pages[body.page])
        return Response(content=svg_str, media_type="image/svg+xml")

    png_bytes = render_png(pages[body.page], dpi=settings.dpi, font_dir=font_dir)
    return Response(content=png_bytes, media_type="image/png")
