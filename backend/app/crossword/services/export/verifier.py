"""PDF verification gate: ensures print-ready vector output with embedded fonts and exact geometry."""
from __future__ import annotations

import io
import re
from typing import Any

from pypdf import PdfReader


class PDFVerificationError(ValueError):
    """Raised when a built PDF fails any print-readiness verification check."""


_VECTOR_PATH_RE = re.compile(rb"(?:^|[\s\[\]])(?:re|m|l|S|f|B)(?:$|[\s])", re.MULTILINE)
_RAW_IMAGE_SUBTYPE_RE = re.compile(rb"/Subtype\s*/Image\b")
_INLINE_IMAGE_RE = re.compile(rb"(?:^|\s)BI\s+.*?\bID\s", re.DOTALL)


def _iter_xobjects(resources, visited=None):
    if visited is None:
        visited = set()
    if resources is None:
        return
    res_obj = resources.get_object() if hasattr(resources, "get_object") else resources
    if not isinstance(res_obj, dict) or "/XObject" not in res_obj:
        return
    xobjs = res_obj["/XObject"].get_object()
    if not isinstance(xobjs, dict):
        return
    for xobj_ref in xobjs.values():
        ref_id = id(xobj_ref)
        if ref_id in visited:
            continue
        visited.add(ref_id)
        xobj = xobj_ref.get_object() if hasattr(xobj_ref, "get_object") else xobj_ref
        if isinstance(xobj, dict):
            yield xobj
            if xobj.get("/Subtype") == "/Form" and "/Resources" in xobj:
                yield from _iter_xobjects(xobj["/Resources"], visited)


def _font_has_embedded_stream(font_obj) -> bool:
    if not isinstance(font_obj, dict):
        return False
    desc_ref = font_obj.get("/FontDescriptor")
    if desc_ref is not None:
        desc = desc_ref.get_object() if hasattr(desc_ref, "get_object") else desc_ref
        if isinstance(desc, dict) and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
            return True
    descendants = font_obj.get("/DescendantFonts")
    if descendants is not None:
        desc_list = descendants.get_object() if hasattr(descendants, "get_object") else descendants
        if isinstance(desc_list, list):
            for df_ref in desc_list:
                df = df_ref.get_object() if hasattr(df_ref, "get_object") else df_ref
                if _font_has_embedded_stream(df):
                    return True
    return False


def verify_pdf(
    pdf_bytes: bytes,
    *,
    expected_page_count: int,
    expected_width_pt: float,
    expected_height_pt: float,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    """Verify PDF contains pure vector paths, zero raster images, embedded fonts, exact trim size & page count, and no transparency."""
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
        if raise_on_failure:
            raise PDFVerificationError("PDF verification failed: invalid PDF header")
        return {"valid": False, "checks": {}, "errors": ["invalid PDF header"]}

    reader = PdfReader(io.BytesIO(pdf_bytes))
    actual_pages = len(reader.pages)

    raster_image_found = bool(_RAW_IMAGE_SUBTYPE_RE.search(pdf_bytes))
    vector_paths_found = False
    trim_mismatches: list[str] = []
    unembedded_fonts: list[str] = []
    total_fonts = 0
    transparency_found = False

    for page_idx, page in enumerate(reader.pages, start=1):
        # 1. Trim size
        mb = page.mediabox
        w = float(mb.width)
        h = float(mb.height)
        if abs(w - expected_width_pt) > 1.0 or abs(h - expected_height_pt) > 1.0:
            trim_mismatches.append(
                f"page {page_idx}: {w:.1f}x{h:.1f}pt != {expected_width_pt:.1f}x{expected_height_pt:.1f}pt"
            )

        # 2. Vector paths & inline raster images in content stream
        contents = page.get_contents()
        if contents is not None:
            try:
                stream_bytes = contents.get_data()
                if _VECTOR_PATH_RE.search(stream_bytes):
                    vector_paths_found = True
                if _INLINE_IMAGE_RE.search(stream_bytes):
                    raster_image_found = True
            except Exception:
                pass

        # 3. Transparency group on page
        group = page.get("/Group")
        if group is not None:
            grp_obj = group.get_object() if hasattr(group, "get_object") else group
            if isinstance(grp_obj, dict) and str(grp_obj.get("/S", "")) == "/Transparency":
                transparency_found = True

        resources = page.get("/Resources")
        res_obj = resources.get_object() if (resources is not None and hasattr(resources, "get_object")) else resources
        if isinstance(res_obj, dict):
            # 4. Raster images in XObjects
            for xobj in _iter_xobjects(res_obj):
                if str(xobj.get("/Subtype", "")) == "/Image":
                    raster_image_found = True

            # 5. Embedded fonts
            if "/Font" in res_obj:
                fonts_dict = res_obj["/Font"].get_object()
                if isinstance(fonts_dict, dict):
                    for fname, fref in fonts_dict.items():
                        total_fonts += 1
                        fobj = fref.get_object() if hasattr(fref, "get_object") else fref
                        if not _font_has_embedded_stream(fobj):
                            base_name = str(fobj.get("/BaseFont", fname)) if isinstance(fobj, dict) else str(fname)
                            if base_name not in unembedded_fonts:
                                unembedded_fonts.append(base_name)

            # 6. Transparency in ExtGState
            if "/ExtGState" in res_obj:
                gs_dict = res_obj["/ExtGState"].get_object()
                if isinstance(gs_dict, dict):
                    for gs_ref in gs_dict.values():
                        gs = gs_ref.get_object() if hasattr(gs_ref, "get_object") else gs_ref
                        if not isinstance(gs, dict):
                            continue
                        smask = gs.get("/SMask")
                        if smask is not None and str(smask) != "/None":
                            transparency_found = True
                        for alpha_key in ("/ca", "/CA"):
                            if alpha_key in gs:
                                try:
                                    if float(gs[alpha_key]) < 0.999:
                                        transparency_found = True
                                except (TypeError, ValueError):
                                    pass

    checks = {
        "zero_raster_images": not raster_image_found,
        "vector_paths_present": vector_paths_found,
        "page_count_matches": actual_pages == expected_page_count,
        "trim_size_matches": len(trim_mismatches) == 0,
        "all_fonts_embedded": total_fonts > 0 and len(unembedded_fonts) == 0,
        "no_transparency": not transparency_found,
    }

    errors: list[str] = []
    if not checks["zero_raster_images"]:
        errors.append("zero_raster_images failed: PDF contains embedded raster images.")
    if not checks["vector_paths_present"]:
        errors.append("vector_paths_present failed: no vector drawing path operators found.")
    if not checks["page_count_matches"]:
        errors.append(
            f"page_count_matches failed: expected {expected_page_count} pages, got {actual_pages}."
        )
    if not checks["trim_size_matches"]:
        errors.append(f"trim_size_matches failed: {'; '.join(trim_mismatches)}.")
    if not checks["all_fonts_embedded"]:
        if total_fonts == 0:
            errors.append("all_fonts_embedded failed: no embedded fonts found in PDF.")
        else:
            errors.append(
                f"all_fonts_embedded failed: unembedded fonts detected ({', '.join(unembedded_fonts)})."
            )
    if not checks["no_transparency"]:
        errors.append("no_transparency failed: PDF uses alpha transparency or soft masks.")

    valid = all(checks.values())
    if not valid and raise_on_failure:
        raise PDFVerificationError("PDF verification failed — " + " ".join(errors))

    return {
        "valid": valid,
        "checks": checks,
        "failed_checks": [k for k, ok in checks.items() if not ok],
        "errors": errors,
        "actual_pages": actual_pages,
        "expected_pages": expected_page_count,
        "width_pt": expected_width_pt,
        "height_pt": expected_height_pt,
    }
