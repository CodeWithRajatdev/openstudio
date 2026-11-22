import io
import time
import xml.etree.ElementTree as ET

import anyio.to_thread
import httpx
import pypdf
import pytest

from app.main import app
from app.wordsearch.export import inspect_pdf_fonts, inspect_pdf_vectors


async def _run_sync_immediate(func, *args, **kwargs):
    return func(*args)


anyio.to_thread.run_sync = _run_sync_immediate


class _SyncASGITransport(httpx.BaseTransport):
    def __init__(self, asgi_app):
        self.app = asgi_app

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in request.headers.items()],
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "scheme": request.url.scheme,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 123),
        }
        in_msgs = [{"type": "http.request", "body": body, "more_body": False}]
        out_msgs = []

        async def receive():
            return in_msgs.pop(0) if in_msgs else {"type": "http.disconnect"}

        async def send(msg):
            out_msgs.append(msg)

        coro = self.app(scope, receive, send)
        try:
            while True:
                coro.send(None)
        except StopIteration:
            pass
        start = next(m for m in out_msgs if m["type"] == "http.response.start")
        resp_body = b"".join(m.get("body", b"") for m in out_msgs if m["type"] == "http.response.body")
        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in start.get("headers", [])]
        return httpx.Response(start["status"], headers=headers, content=resp_body, request=request)


client = httpx.Client(transport=_SyncASGITransport(app), base_url="http://testserver")
WORDS = ["APPLE", "MANGO", "ORANGE", "BANANA", "GRAPE", "LEMON"]


def csv_upload(text, name="w.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


def test_health():
    r = client.get("/api/wordsearch/health").json()
    assert r["ok"] and "rounded_rect" in r["highlight_styles"]


def test_import_returns_chapters_issues_and_errors():
    r = client.post("/api/wordsearch/import", files=csv_upload("Chapter,Word\nA,apple\nA,Apple\nB,tiger\n"))
    j = r.json()
    assert r.status_code == 200 and j["summary"]["chapters"] == 2
    assert [i["code"] for i in j["issues"]] == ["duplicate_in_chapter"]
    assert j["chapters"][0]["words"][0]["raw"] == "apple"
    bad = client.post("/api/wordsearch/import", files=csv_upload("x", "w.pdf"))
    assert bad.status_code == 400 and "Unsupported" in bad.json()["detail"]


def test_validate_and_remove_duplicates_roundtrip():
    j = client.post("/api/wordsearch/import", files=csv_upload("Chapter,Word\nA,apple\nA,Apple\n")).json()
    v = client.post("/api/wordsearch/bank/validate", json={"chapters": j["chapters"]}).json()
    assert not v["ready"]
    d = client.post("/api/wordsearch/bank/remove-duplicates", json={"chapters": j["chapters"]}).json()
    assert [r["word"] for r in d["removed"]] == ["Apple"] and d["issues"] == []
    assert len(d["chapters"][0]["words"]) == 1


def test_preview_returns_valid_svg_and_key():
    r = client.post("/api/wordsearch/preview", json={"words": WORDS, "title": "Fruits",
                                          "seed": 5}).json()
    ET.fromstring(r["puzzle_svg"]); ET.fromstring(r["answer_svg"])
    assert r["seed"] == 5 and len(r["key"]) == len(WORDS)
    again = client.post("/api/wordsearch/preview", json={"words": WORDS, "title": "Fruits",
                                              "seed": 5}).json()
    assert again["puzzle_svg"] == r["puzzle_svg"]


def test_preview_failures_are_clear_422s():
    r = client.post("/api/wordsearch/preview", json={"words": ["EXTRAORDINARILY"],
                    "config": {"sizing_mode": "manual", "rows": 5, "cols": 5}})
    assert r.status_code == 422 and r.json()["failed_words"] == ["EXTRAORDINARILY"]
    r = client.post("/api/wordsearch/preview", json={"words": WORDS,
                    "layout": {"page_width": 40, "page_height": 50, "margin": 8}})
    assert r.status_code == 422 and "layout" in r.json()["detail"].lower()
    r = client.post("/api/wordsearch/preview", json={"words": WORDS, "config": {"rows": 0}})
    assert r.status_code == 422


def test_preview_answers_sheet():
    items = [{"title": f"C{i}", "words": WORDS} for i in range(4)]
    r = client.post("/api/wordsearch/preview/answers", json={"items": items, "per_page": 4}).json()
    ET.fromstring(r["svg"])
    assert client.post("/api/wordsearch/preview/answers",
                       json={"items": items, "per_page": 2}).status_code == 422


def wait(job_id, key="status", until=("done", "cancelled"), timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/wordsearch/jobs/{job_id}").json()
        if j[key] in until:
            return j
        time.sleep(0.05)
    raise AssertionError("timeout")


def test_job_lifecycle_failures_subset_seeds_export_download():
    chapters = [{"index": i, "title": f"Ch {i + 1}", "words": WORDS} for i in range(4)]
    chapters.append({"index": 4, "title": "Broken", "words": ["CAT", "???"]})
    spec = {"chapters": chapters, "base_seed": 10,
            "config": {"reverse": True}, "seed_overrides": {"2": 777}}
    j = client.post("/api/wordsearch/jobs", json=spec).json()
    j = wait(j["id"])
    assert (j["succeeded"], j["failed"], j["done"], j["total"]) == (4, 1, 5, 5)
    assert j["chapters"][2]["seed"] == 777 and j["chapters"][0]["seed"] == 10
    assert "???" in j["chapters"][4]["failed_words"]

    # Individual chapter SVG endpoint is removed; partial books cannot be exported.
    assert client.get(f"/api/wordsearch/jobs/{j['id']}/chapters/0/svg").status_code == 404
    assert client.post(f"/api/wordsearch/jobs/{j['id']}/retry-failed").json()["total"] == 1
    wait(j["id"])

    assert client.get(f"/api/wordsearch/jobs/{j['id']}/download").status_code == 409
    partial = client.post(f"/api/wordsearch/jobs/{j['id']}/export", json={"project_name": "My Book",
                                                               "per_page_answers": 2})
    assert partial.status_code == 409
    assert "Cannot export a partial book" in partial.json()["detail"]

    # Now run a clean 4-chapter job where all chapters succeed -> exports single vector PDF.
    j_ok = client.post("/api/wordsearch/jobs", json={"chapters": chapters[:4], "base_seed": 10,
                                          "config": {"reverse": True}, "seed_overrides": {"2": 777}}).json()
    j_ok = wait(j_ok["id"])
    assert (j_ok["succeeded"], j_ok["failed"]) == (4, 0)
    r_exp = client.post(f"/api/wordsearch/jobs/{j_ok['id']}/export", json={"project_name": "My Book",
                                                                "per_page_answers": 2})
    assert r_exp.status_code == 200
    t = time.time()
    while time.time() - t < 60:
        e = client.get(f"/api/wordsearch/jobs/{j_ok['id']}").json()["export"]
        if e["state"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert e["state"] == "done", e
    assert e["name"] == "my-book.pdf"
    dl = client.get(f"/api/wordsearch/jobs/{j_ok['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/pdf")
    assert 'filename="my-book.pdf"' in dl.headers["content-disposition"]
    assert dl.content[:5] == b"%PDF-"
    reader = pypdf.PdfReader(io.BytesIO(dl.content))
    # 4 puzzle pages + 2 solution pages (2 per page) = 6 pages
    assert len(reader.pages) == 6
    assert all(f["emb"] for f in inspect_pdf_fonts(dl.content))


def test_job_cancel_and_layout_failure_marks_chapter_failed():
    chapters = [{"index": i, "title": f"C{i}", "words": WORDS} for i in range(3)]
    j = client.post("/api/wordsearch/jobs", json={
        "chapters": chapters,
        "layout": {"page_width": 40, "page_height": 40, "margin": 10, "min_cell_size": 3.5}}).json()
    j = wait(j["id"])
    assert j["failed"] == 3 and "does not fit the page" in j["chapters"][0]["error"]
    big = [{"index": i, "title": f"C{i}", "words": WORDS} for i in range(150)]
    j2 = client.post("/api/wordsearch/jobs", json={"chapters": big}).json()
    client.post(f"/api/wordsearch/jobs/{j2['id']}/cancel")
    j2 = wait(j2["id"])
    assert j2["status"] == "cancelled" and j2["done"] < 150


def test_unknown_job_and_export_guards():
    assert client.get("/api/wordsearch/jobs/nope").status_code == 404


def xlsx_upload(rows, name="w.xlsx"):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    for r in rows:
        ws.append([r])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return {"file": (name, buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


def test_import_blank_rows_with_expected_words_reports_invalid_chapter():
    rows = [f"w{chr(97+i)}x" for i in range(20)] + [None] + [f"v{chr(97+i)}y" for i in range(18)]
    r = client.post("/api/wordsearch/import", files=xlsx_upload(rows), data={"expected_words": "20"}).json()
    assert r["summary"]["chapters"] == 2 and r["summary"]["valid_chapters"] == 1
    bad = [i for i in r["issues"] if i["code"] == "wrong_word_count"]
    assert bad[0]["chapter_index"] == 1 and (bad[0]["expected"], bad[0]["actual"]) == (20, 18)
    assert bad[0]["message"] == "Chapter 2 has 18 words. Expected 20. Missing 2."
    assert r["sheets"][0]["name"] == "Sheet" and r["size_bytes"] > 0


def test_validate_endpoint_enforces_expected_words():
    ch = [{"title": "A", "words": [{"id": i, "raw": "x", "text": "abc"[:1] + chr(100 + i)} for i in range(3)]}]
    v = client.post("/api/wordsearch/bank/validate", json={"chapters": ch, "expected_words": 4}).json()
    assert not v["ready"] and v["issues"][0]["code"] == "wrong_word_count"
    assert client.post("/api/wordsearch/bank/validate", json={"chapters": ch, "expected_words": 3}).json()["ready"]


def test_job_refuses_wrong_word_counts_server_side():
    ok = {"index": 0, "title": "A", "words": WORDS}
    bad = {"index": 1, "title": "B", "words": WORDS[:4]}
    r = client.post("/api/wordsearch/jobs", json={"chapters": [ok, bad], "expected_words": 6})
    assert r.status_code == 422 and "Chapter 2 (B) has 4 words" in r.json()["detail"] and r.json()["wrong_chapters"] == [1]
    assert client.post("/api/wordsearch/jobs", json={"chapters": [ok], "expected_words": 6}).status_code == 200


# ---- Section 13 acceptance scenarios + Step C customization ---------------
def _word_pool(n, prefix="WORD"):
    out = []
    for i in range(n):
        a, b = divmod(i, 26)
        out.append(f"{prefix}{chr(65 + a)}{chr(65 + b)}")
    return out


def test_acceptance_scenarios_1_through_8():
    # Test 1: Excel import with 10 chapters x 20 words separated by blank rows
    excel_rows = []
    for ch in range(10):
        if ch > 0:
            excel_rows.append(None)
        excel_rows.extend(_word_pool(20, f"CH{chr(65 + ch)}"))
    r1 = client.post("/api/wordsearch/import", files=xlsx_upload(excel_rows, "t1.xlsx"),
                     data={"expected_words": "20"}).json()
    assert r1["summary"]["chapters"] == 10
    assert r1["summary"]["words"] == 200
    assert r1["summary"]["valid_chapters"] == 10 and r1["summary"]["invalid_chapters"] == 0

    # Test 2: TXT import with 10 chapters x 20 words separated by blank lines
    txt_blocks = ["\n".join(_word_pool(20, f"TX{chr(65 + ch)}")) for ch in range(10)]
    txt_bytes = "\n\n".join(txt_blocks)
    r2 = client.post("/api/wordsearch/import", files=csv_upload(txt_bytes, "t2.txt"),
                     data={"expected_words": "20"}).json()
    assert r2["summary"]["chapters"] == 10 and r2["summary"]["words"] == 200
    assert r2["summary"]["valid_chapters"] == 10

    # Test 3: Invalid word count (10 chapters where Chapter 3 has 18 words)
    short_blocks = list(txt_blocks)
    short_blocks[2] = "\n".join(_word_pool(18, "TXC"))
    r3 = client.post("/api/wordsearch/import", files=csv_upload("\n\n".join(short_blocks), "t3.txt"),
                     data={"expected_words": "20"}).json()
    assert r3["summary"]["invalid_chapters"] == 1
    err3 = [i for i in r3["issues"] if i["code"] == "wrong_word_count"][0]
    assert err3["chapter_index"] == 2 and err3["actual"] == 18 and err3["expected"] == 20

    # Test 4: Extra words (22 words when limit is 20 -> flagged, never silently removed)
    extra_blocks = list(txt_blocks)
    extra_blocks[3] = "\n".join(_word_pool(22, "TXD"))
    r4 = client.post("/api/wordsearch/import", files=csv_upload("\n\n".join(extra_blocks), "t4.txt"),
                     data={"expected_words": "20"}).json()
    assert len(r4["chapters"][3]["words"]) == 22
    err4 = [i for i in r4["issues"] if i["code"] == "wrong_word_count"][0]
    assert err4["chapter_index"] == 3 and err4["actual"] == 22

    # Test 5 & 6: Long words + Preview with BookBolt customization settings
    long_words = ["EXTRAORDINARY", "RESPONSIBILITY", "COMMUNICATION", "ENVIRONMENT",
                  "UNDERSTANDING", "COLLABORATION", "DETERMINATION", "INFRASTRUCTURE",
                  "TRANSFORMATION", "SUSTAINABILITY", "ACCOUNTABILITY", "ADMINISTRATION"]
    layout_cfg = {
        "page_width": 215.9, "page_height": 279.4,
        "margin": 15, "extra_margins": True, "margin_top": 5, "margin_left": 5,
        "grid_font": "Open Sans", "grid_font_weight": "normal",
        "letter_size_ratio": 0.5, "letter_color": "#000000",
        "grid_line_width": 0.25, "grid_line_color": "#222222",
        "cell_color": "#fafafa", "border_width": 0.4, "border_color": "#111111",
        "puzzle_align": "center", "clue_type": "columns", "clue_sort": "short_long",
        "clue_align": "center", "clue_font": "Open Sans", "clue_size_ratio": 0.03,
        "title_enabled": True, "title_mode": "custom",
        "title_text": "Puzzle #PUZZLE_NUMBER", "title_start_number": 1,
        "solution_font": "Open Sans", "highlight_color": "#d62839",
    }
    p_res = client.post("/api/wordsearch/preview", json={
        "words": long_words, "title": "Chapter 5", "index": 4, "seed": 99,
        "layout": layout_cfg, "answer_style": "rounded_rect",
    })
    assert p_res.status_code == 200
    pj = p_res.json()
    assert pj["rows"] >= 14 and pj["cols"] >= 14
    assert len(pj["key"]) == 12
    assert pj["resolved_title"] == "Puzzle #5"
    assert "Puzzle #5" in pj["puzzle_svg"]
    ET.fromstring(pj["puzzle_svg"]); ET.fromstring(pj["answer_svg"])

    # Test 7 & 8: Bulk generation of 100 chapters + Single-PDF Export
    bulk_chapters = [
        {"index": i, "title": f"Chapter {i + 1}", "words": _word_pool(10, f"B{chr(65 + i // 26)}{chr(65 + i % 26)}")}
        for i in range(100)
    ]
    job = client.post("/api/wordsearch/jobs", json={
        "chapters": bulk_chapters, "base_seed": 500, "expected_words": 10,
        "layout": layout_cfg,
    }).json()
    job = wait(job["id"], timeout=120)
    assert job["succeeded"] == 100 and job["failed"] == 0
    assert [c["index"] for c in job["chapters"]] == list(range(100))

    client.post(f"/api/wordsearch/jobs/{job['id']}/export", json={
        "project_name": "Hundred Puzzle Book", "per_page_answers": 6,
        "answer_style": "rounded_rect", "page_numbers": True, "include_answers": True,
    })
    t = time.time()
    while time.time() - t < 120:
        ex = client.get(f"/api/wordsearch/jobs/{job['id']}").json()["export"]
        if ex["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert ex["state"] == "done", ex
    assert ex["name"] == "hundred-puzzle-book.pdf"
    dl = client.get(f"/api/wordsearch/jobs/{job['id']}/download")
    assert dl.headers["content-type"].startswith("application/pdf")
    assert 'filename="hundred-puzzle-book.pdf"' in dl.headers["content-disposition"]
    vec = inspect_pdf_vectors(dl.content)
    # 100 puzzle pages + ceil(100/6)=17 solution pages + 1 blank page = 118 total pages
    assert vec["pages"] == 118
    assert vec["images"] == 0
    assert vec["vector_ops"] > 1000
    assert all(f["emb"] for f in vec["pdf_fonts"])


def test_sqlite_job_persistence_survives_restart_and_disk_cache_export(tmp_path):
    from pathlib import Path
    from app.wordsearch.api.jobs import JobStore
    from app.wordsearch.api.schemas import ExportIn, JobIn

    db_file = tmp_path / "test_jobs.sqlite3"
    cache_dir = tmp_path / "pdf_cache"
    store1 = JobStore(db_path=db_file, cache_dir=cache_dir)
    assert not hasattr(store1, "jobs")

    spec = JobIn.model_validate({
        "chapters": [{"index": 0, "title": "Ch 1", "words": WORDS},
                     {"index": 1, "title": "Ch 2", "words": WORDS}],
        "base_seed": 77,
        "config": {"reverse": True, "rows": 14, "cols": 14},
        "layout": {"page_width": 215.9, "page_height": 279.4, "margin": 12.0},
    })
    started = store1.start(spec)
    t0 = time.time()
    while time.time() - t0 < 30:
        if store1.snapshot(started.id)["status"] in ("done", "cancelled"):
            break
        time.sleep(0.02)

    # Simulate a server restart with a brand-new JobStore instance reading the same SQLite DB.
    store2 = JobStore(db_path=db_file, cache_dir=cache_dir)
    restored = store2.get(started.id)
    snap = restored.snapshot()
    assert snap["status"] == "done"
    assert snap["succeeded"] == 2 and snap["failed"] == 0
    assert restored.spec.base_seed == 77
    assert restored.spec.config.reverse is True
    assert restored.spec.layout.margin == 12.0

    assert store2.start_export(restored, ExportIn(project_name="Persisted Book", per_page_answers=2))
    t0 = time.time()
    while time.time() - t0 < 30:
        if store2.snapshot(started.id)["export"]["state"] in ("done", "error"):
            break
        time.sleep(0.02)

    final_job = store2.get(started.id)
    assert final_job.export_state == "done"
    assert final_job.export_path is not None
    assert Path(final_job.export_path).exists()
    assert final_job.export_size == Path(final_job.export_path).stat().st_size > 0


