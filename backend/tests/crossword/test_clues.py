"""Checkpoint 3 tests: clue validator, dictionary providers, AI provider, modes, reuse, jobs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.crossword.config import Settings
from app.crossword.db import Base, create_db_engine, get_db, get_session_factory
from app.main import app
from app.crossword.models import Clue, Word
from app.crossword.services.clues.ai import FakeAIProvider, get_ai_provider
from app.crossword.services.clues.dictionary import (
    JsonlDictionaryProvider,
    NullDictionaryProvider,
    WordNetDictionaryProvider,
    gloss_to_clue,
)
from app.crossword.services.clues.service import (
    create_clue_generation_job,
    execute_clue_generation_job,
    get_collection_clues_summary,
)
from app.crossword.services.clues.validator import validate_clue


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "clues_test.db"
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
    app.dependency_overrides[get_session_factory] = lambda: TestingSessionLocal
    with TestClient(app) as client:
        yield client, TestingSessionLocal
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_clue_validator_rules():
    assert validate_clue("Crisp orchard fruit.", "APPLE").valid is True
    assert validate_clue("", "APPLE").valid is False
    assert validate_clue("uncapitalized fruit.", "APPLE").valid is False
    assert validate_clue('Unbalanced "quote.', "APPLE").valid is False
    assert validate_clue("Unbalanced (paren.", "APPLE").valid is False
    assert validate_clue("Here is a clue: sweet fruit.", "APPLE").valid is False
    assert validate_clue("Clue: sweet fruit.", "APPLE").valid is False
    assert validate_clue("Sweet apple pie.", "APPLE").valid is False
    assert validate_clue("Basket of apples.", "APPLE").valid is False


def test_gloss_to_clue_and_jsonl(tmp_path: Path):
    clue = gloss_to_clue("a sweet (red or green) fruit; grows on trees", "APPLE", difficulty="easy")
    assert clue == "A sweet fruit."

    # WordNet exact lemma vs inflected form vs proper noun
    wn_prov = WordNetDictionaryProvider()
    assert wn_prov.lookup("apple", "APPLE", difficulty="medium") is not None
    assert wn_prov.lookup("apples", "APPLES", difficulty="medium") is None
    assert wn_prov.lookup("france", "FRANCE", difficulty="medium") is None

    # JSONL provider
    jsonl_path = tmp_path / "dict.jsonl"
    jsonl_path.write_text(
        json.dumps({"word": "zephyr", "definition": "a gentle breeze (from the west); mild wind"}) + "\n",
        encoding="utf-8",
    )
    jprov = JsonlDictionaryProvider(jsonl_path)
    assert jprov.lookup("zephyr", "ZEPHYR", difficulty="easy") == "A gentle breeze."


def test_clue_modes_reuse_and_verification(db_setup):
    client, SessionLocal = db_setup

    # Stage & commit a small collection:
    # - mango (has imported clue)
    # - apple (exact lemma in WordNet)
    # - apples (inflected -> goes to AI)
    csv_bytes = (
        "Word,Clue\n"
        "mango,Tropical stone fruit\n"
        "apple,\n"
        "apples,\n"
    ).encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("words.csv", csv_bytes, "text/csv")}).json()
    commit = client.post(f"/api/imports/{imp['id']}/commit").json()
    col_id = commit["collections"][0]["id"]

    fake_ai = FakeAIProvider(verify_succeeds=True)
    wn_prov = WordNetDictionaryProvider()

    # 1. Manual mode: generates nothing, reports missing words
    with SessionLocal() as db:
        summary_manual = get_collection_clues_summary(db, col_id, mode="manual", difficulty="medium")
        assert summary_manual["clue_status"] == "incomplete"
        assert [m["answer"] for m in summary_manual["missing_words"]] == ["APPLE", "APPLES"]

    # 2. Hybrid mode with verify=True
    with SessionLocal() as db:
        job = create_clue_generation_job(
            db, collection_id=col_id, mode="hybrid", difficulty="medium", verify=True
        )
        job_id = job.id

    execute_clue_generation_job(
        job_id, SessionLocal, dictionary_provider=wn_prov, ai_provider=fake_ai
    )

    job_res = client.get(f"/api/jobs/{job_id}").json()
    assert job_res["status"] == "completed"
    assert job_res["completed"] == 3
    assert job_res["failed"] == 0
    assert job_res["result"]["reused"] == 1        # mango (import)
    assert job_res["result"]["from_dictionary"] == 1  # apple (WordNet)
    assert job_res["result"]["from_ai"] == 1       # apples (FakeAI)
    assert len(fake_ai.calls) == 1

    clues_res = client.get(f"/api/collections/{col_id}/clues?mode=hybrid&difficulty=medium").json()
    assert clues_res["clue_status"] == "complete"
    by_ans = {it["answer"]: it["active_clue"] for it in clues_res["items"]}
    assert by_ans["MANGO"]["source"] == "import"
    assert by_ans["APPLE"]["source"] == "dictionary"
    assert by_ans["APPLE"]["status"] == "needs_review"
    assert by_ans["APPLES"]["source"] == "ai"
    assert by_ans["APPLES"]["status"] == "approved"

    # 3. Re-running hybrid without regenerate makes 0 AI calls (reuses approved clues)
    with SessionLocal() as db:
        job2 = create_clue_generation_job(
            db, collection_id=col_id, mode="hybrid", difficulty="medium", verify=True
        )
        job2_id = job2.id
    execute_clue_generation_job(
        job2_id, SessionLocal, dictionary_provider=wn_prov, ai_provider=fake_ai
    )
    assert len(fake_ai.calls) == 1  # no new AI call!
    assert client.get(f"/api/jobs/{job2_id}").json()["result"]["reused"] == 3

    # 4. Automatic mode ignores user clue for MANGO (generates one) but never deletes the import clue
    with SessionLocal() as db:
        job3 = create_clue_generation_job(
            db, collection_id=col_id, mode="automatic", difficulty="medium", verify=False
        )
        job3_id = job3.id
    execute_clue_generation_job(
        job3_id, SessionLocal, dictionary_provider=NullDictionaryProvider(), ai_provider=fake_ai
    )
    with SessionLocal() as db:
        mango = db.scalar(select(Word).where(Word.answer == "MANGO"))
        mango_clues = list(db.scalars(select(Clue).where(Clue.word_id == mango.id)).all())
        sources = {c.source for c in mango_clues}
        assert "import" in sources
        assert "ai" in sources
        # Unverified AI clue has status needs_review
        ai_clue = next(c for c in mango_clues if c.source == "ai")
        assert ai_clue.status == "needs_review"

        # Bulk approve
        approve_res = client.post("/api/clues/bulk-approve", json={"collection_id": col_id})
        assert approve_res.status_code == 200
        assert approve_res.json()["approved_count"] >= 1


def test_api_generate_endpoint_and_manual_edit(db_setup, monkeypatch):
    client, _ = db_setup
    monkeypatch.setenv("AI_PROVIDER", "fake")
    monkeypatch.setenv("DICTIONARY_PROVIDER", "none")
    from app.crossword.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_ai_provider(Settings(ai_provider="fake")).name == "fake"

        csv_bytes = "Word\nquartz\n".encode("utf-8")
        imp = client.post("/api/imports", files={"file": ("q.csv", csv_bytes, "text/csv")}).json()
        col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

        gen = client.post(
            "/api/clues/generate",
            json={"collection_id": col_id, "mode": "automatic", "difficulty": "hard", "verify": True},
        )
        assert gen.status_code == 200
        job_id = gen.json()["job_id"]
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "completed"
        assert job["result"]["from_ai"] == 1

        summary = client.get(f"/api/collections/{col_id}/clues?mode=automatic&difficulty=hard").json()
        word_id = summary["items"][0]["word_id"]
        clue_id = summary["items"][0]["active_clue"]["id"]

        patched = client.patch(f"/api/clues/{clue_id}", json={"text": "Crystalline mineral.", "status": "approved"})
        assert patched.status_code == 200
        assert patched.json()["text"] == "Crystalline mineral."

        created = client.post(
            f"/api/words/{word_id}/clues",
            json={"text": "Hard silicate mineral.", "difficulty": "hard"},
        )
        assert created.status_code == 201
        assert created.json()["source"] == "manual"
    finally:
        get_settings.cache_clear()
