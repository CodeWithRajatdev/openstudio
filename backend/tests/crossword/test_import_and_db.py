"""Checkpoint 2 tests: DB models, CSV/Excel/TXT import, report, staging, commit, collections."""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db
from app.main import app
from app.crossword.models import Clue, Collection, Word


@pytest.fixture()
def client_and_session(tmp_path: Path):
    db_path = tmp_path / "test.db"
    test_engine = create_db_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, future=True)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_csv_import_report_and_commit(client_and_session):
    client, SessionLocal = client_and_session
    csv_content = (
        "Word,Clue,Difficulty,Group\n"
        "ice-cream,Frozen dessert,e,Chapter 1\n"
        "café,Coffee shop,med,Chapter 1\n"
        "ICE CREAM,Duplicate in same group,1,Chapter 1\n"
        "r2d2,Invalid digits,2,Chapter 1\n"
        "a,Too short,3,Chapter 1\n"
        ",,,\n"
        "planet,Orbits a star,expert,Chapter 2\n"
        "cafe,Cross-group duplicate,hard,Chapter 2\n"
    ).encode("utf-8-sig")

    res = client.post(
        "/api/imports",
        files={"file": ("vocab.csv", csv_content, "text/csv")},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "staged"
    assert data["source_format"] == "csv"

    report = data["report"]
    assert report["valid_count"] == 4
    assert report["duplicate_count"] == 1
    assert report["invalid_count"] == 2
    assert report["empty_row_count"] == 1
    assert report["group_count"] == 2

    # Warnings: unknown difficulty 'expert' + cross-group duplicate 'CAFE'
    warning_types = {w["type"] for w in report["warnings"]}
    assert warning_types == {"unknown_difficulty", "cross_group_duplicate"}

    # Verify nothing saved to collections yet before commit
    assert client.get("/api/collections").json() == []

    # Fetch staged batch
    get_res = client.get(f"/api/imports/{data['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == data["id"]

    # Commit
    commit_res = client.post(f"/api/imports/{data['id']}/commit")
    assert commit_res.status_code == 200, commit_res.text
    commit_data = commit_res.json()
    assert commit_data["status"] == "committed"
    assert commit_data["words_created"] == 3  # ICECREAM, CAFE, PLANET
    assert commit_data["words_reused"] == 1   # CAFE in Chapter 2
    assert commit_data["clues_created"] == 4
    assert len(commit_data["collections"]) == 2

    # Double commit rejected
    assert client.post(f"/api/imports/{data['id']}/commit").status_code == 409

    # Verify collections API
    cols = client.get("/api/collections").json()
    assert len(cols) == 2
    ch1 = next(c for c in cols if c["name"] == "Chapter 1")
    ch1_detail = client.get(f"/api/collections/{ch1['id']}").json()
    assert [w["answer"] for w in ch1_detail["words"]] == ["ICECREAM", "CAFE"]
    assert ch1_detail["words"][0]["display"] == "ice-cream"
    assert ch1_detail["words"][0]["difficulty"] == "easy"
    assert ch1_detail["words"][0]["clues"][0]["source"] == "import"
    assert ch1_detail["words"][0]["clues"][0]["status"] == "approved"

    with SessionLocal() as db:
        assert len(db.scalars(select(Word)).all()) == 3
        assert len(db.scalars(select(Clue)).all()) == 4
        assert len(db.scalars(select(Collection)).all()) == 2


def test_csv_no_header_semicolon_latin1(client_and_session):
    client, _ = client_and_session
    raw = "apple;Red fruit;1\nbanana;Yellow fruit;2\n".encode("latin-1")
    res = client.post(
        "/api/imports",
        files={"file": ("list.csv", raw, "text/csv")},
        data={"collection_name": "Fruits"},
    )
    assert res.status_code == 200
    report = res.json()["report"]
    assert report["valid_count"] == 2
    assert report["groups"][0]["name"] == "Fruits"
    assert report["groups"][0]["words"][0]["answer"] == "APPLE"
    assert report["groups"][0]["words"][0]["clue"] == "Red fruit"
    assert report["groups"][0]["words"][0]["difficulty"] == "easy"


def test_excel_multisheet_import(client_and_session):
    client, _ = client_and_session
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Animals"
    ws1.append(["Word", "Clue", "Difficulty"])
    ws1.append(["tiger", "Striped big cat", "easy"])
    ws1.append(["whale", "Ocean mammal", "medium"])

    ws2 = wb.create_sheet("Space")
    ws2.append(["Word", "Clue"])
    ws2.append(["orbit", "Curved path"])
    ws2.append(["123", "Bad"])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    res = client.post(
        "/api/imports",
        files={
            "file": (
                "book.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source_format"] == "excel"
    report = body["report"]
    assert report["group_count"] == 2
    assert report["valid_count"] == 3
    assert report["invalid_count"] == 1
    assert [g["name"] for g in report["groups"]] == ["Animals", "Space"]


def test_txt_blank_row_groups_and_paste(client_and_session):
    client, _ = client_and_session
    text = "alpha\nbeta\n\ngamma\ndelta\n"
    res = client.post("/api/imports/paste", json={"text": text})
    assert res.status_code == 200
    report = res.json()["report"]
    assert report["group_count"] == 2
    assert report["valid_count"] == 4
    assert [g["name"] for g in report["groups"]] == ["Group 1", "Group 2"]

    commit = client.post(f"/api/imports/{res.json()['id']}/commit")
    assert commit.status_code == 200
    assert len(commit.json()["collections"]) == 2

