"""Phase 2 tests: grid quality metrics, reproducible auto-retry, Needs attention actions & plain-language errors."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.crossword.db import Base, create_db_engine, get_db, get_session_factory
from app.crossword.engine import EngineSettings
from app.main import app
from app.crossword.services.bulk import create_bulk_generation_job, execute_bulk_generation_job
from app.crossword.services.clues.ai import FakeAIProvider
from app.crossword.services.clues.dictionary import NullDictionaryProvider


@pytest.fixture()
def db_setup(tmp_path: Path):
    db_path = tmp_path / "phase2_test.db"
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


def test_quality_metrics_low_and_high_density_outside_engine():
    from app.crossword.services.quality import compute_grid_quality_metrics, evaluate_quality_threshold

    # High-density 3x3 grid: 7 letter cells out of 9, 2 crossings at (0,0) and (0,2)
    high_grid = ["CAT", "A#O", "R#P"]
    high_entries = [
        {"answer": "CAT", "row": 0, "col": 0, "direction": "A"},
        {"answer": "CAR", "row": 0, "col": 0, "direction": "D"},
        {"answer": "TOP", "row": 0, "col": 2, "direction": "D"},
    ]
    high_m = compute_grid_quality_metrics(high_grid, high_entries, unplaced=[])
    assert high_m["letter_cells"] == 7
    assert high_m["total_cells"] == 9
    assert high_m["density"] == pytest.approx(7 / 9, abs=1e-4)
    assert high_m["crossing_count"] == 2
    high_q = evaluate_quality_threshold(high_m, validation_valid=True, min_density=0.50, min_crossings=1)
    assert high_q["meets_threshold"] is True
    assert high_q["status"] == "Ready"

    # Low-density 10x10 sparse grid: 9 letter cells out of 100, 1 crossing
    low_grid = [
        "APPLE#####",
        "L#########",
        "P#########",
        "H#########",
        "A#########",
    ] + ["##########"] * 5
    low_entries = [
        {"answer": "APPLE", "row": 0, "col": 0, "direction": "A"},
        {"answer": "ALPHA", "row": 0, "col": 0, "direction": "D"},
    ]
    low_m = compute_grid_quality_metrics(low_grid, low_entries, unplaced=[])
    assert low_m["letter_cells"] == 9
    assert low_m["total_cells"] == 100
    assert low_m["density"] == pytest.approx(0.09, abs=1e-4)
    assert low_m["crossing_count"] == 1
    low_q = evaluate_quality_threshold(low_m, validation_valid=True, min_density=0.25, min_crossings=1)
    assert low_q["meets_threshold"] is False
    assert low_q["density_ok"] is False
    assert low_q["status"] == "Needs attention"


def test_job_runner_auto_retry_reproducibility_and_winning_seed_strategy(db_setup):
    client, SessionLocal = db_setup
    csv_bytes = (
        "Word,Clue\n"
        "apple,Crisp orchard fruit.\n"
        "planet,Body orbiting a star.\n"
        "elephant,Largest land mammal.\n"
        "tiger,Striped big cat.\n"
        "eagle,Bird of prey.\n"
        "river,Flowing stream.\n"
    ).encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("vocab.csv", csv_bytes, "text/csv")}).json()
    col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

    with SessionLocal() as db:
        job = create_bulk_generation_job(
            db,
            collection_ids=[col_id],
            engine_settings=EngineSettings(
                attempts_per_size=1,
                polish_attempts=0,
                max_nodes_per_attempt=300,
                seed=1,
                strategy="auto",
            ),
            clue_mode="hybrid",
            difficulty="medium",
            generate_missing_clues=False,
            min_density=0.20,
            auto_retry=True,
            max_retries=3,
            max_workers=1,
        )
        job_id = job.id

    execute_bulk_generation_job(
        job_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(),
        use_process_pool=False,
    )

    job_data = client.get(f"/api/jobs/{job_id}").json()
    assert job_data["status"] == "completed"
    p_info = job_data["result"]["puzzles"][0]
    assert "winning_seed" in p_info
    assert "winning_strategy" in p_info
    assert p_info["attempts_tried"] >= 1
    assert isinstance(p_info["retry_history"], list) and len(p_info["retry_history"]) >= 1
    assert p_info["quality"]["density"] > 0
    assert p_info["quality"]["crossing_count"] >= 1
    assert p_info["hit_time_limit"] is False

    # Reproducibility: regenerating with the recorded winning_seed & winning_strategy yields identical grid
    saved_puz = client.get(f"/api/puzzles/{p_info['puzzle_id']}").json()
    repro = client.post(
        "/api/puzzles/generate",
        json={
            "collection_id": col_id,
            "settings": {
                "seed": p_info["winning_seed"],
                "strategy": p_info["winning_strategy"],
                "attempts_per_size": 1,
                "polish_attempts": 0,
                "max_nodes_per_attempt": 300,
            },
        },
    ).json()
    assert repro["grid"] == saved_puz["grid"]
    assert [(e["answer"], e["row"], e["col"], e["direction"]) for e in repro["entries"]] == [
        (e["answer"], e["row"], e["col"], e["direction"]) for e in saved_puz["entries"]
    ]


def test_below_threshold_marked_needs_attention_never_dropped(db_setup):
    client, SessionLocal = db_setup
    pid = client.post(
        "/api/projects",
        json={
            "name": "Threshold Project",
            "settings": {"grid": {"min_density": 0.95}},
        },
    ).json()["id"]

    # Chapter 1: ZZZ shares no letters with CAT/CAR -> unplaced
    # Chapter 2: CAT/CAR/TAR -> valid, but cannot meet min_density=0.95
    paste_text = (
        "Chapter,Word,Clue\n"
        "Ch1 Unplaced,cat,Small feline\n"
        "Ch1 Unplaced,car,Road vehicle\n"
        "Ch1 Unplaced,zzz,Sleeping sound\n"
        "Ch2 LowDensity,cat,Small feline\n"
        "Ch2 LowDensity,car,Road vehicle\n"
        "Ch2 LowDensity,tar,Road pitch\n"
    )
    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    proj = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept").json()["project"]
    col_ids = [ch["id"] for ch in proj["chapters"]]

    with SessionLocal() as db:
        job = create_bulk_generation_job(
            db,
            collection_ids=col_ids,
            engine_settings=EngineSettings(attempts_per_size=1, polish_attempts=0, max_nodes_per_attempt=200),
            min_density=0.95,
            auto_retry=True,
            max_retries=2,
            max_workers=1,
            generate_missing_clues=False,
        )
        job_id = job.id

    execute_bulk_generation_job(
        job_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(),
        use_process_pool=False,
    )

    job_data = client.get(f"/api/jobs/{job_id}").json()
    puzzles = job_data["result"]["puzzles"]
    assert len(puzzles) == 2  # Never silently dropped
    assert len(job_data["result"]["needs_attention"]) == 2
    for p in puzzles:
        assert p["status"] == "Needs attention"
        assert p["quality_status"] == "Needs attention"
        assert p["needs_attention"] is True

    ch1_puz = next(p for p in puzzles if p["title"] == "Ch1 Unplaced")
    assert ch1_puz["placed_count"] == 2
    assert ch1_puz["unplaced_count"] == 1
    assert ch1_puz["attempts_tried"] == 3  # 1 initial + 2 retries

    # Project serialization reflects "Needs attention"
    refreshed_proj = client.get(f"/api/projects/{pid}").json()
    assert all(ch["status"] == "Needs attention" for ch in refreshed_proj["chapters"])


def test_needs_attention_inline_actions_edit_remove_larger_grid_new_seed(db_setup):
    client, _ = db_setup
    pid = client.post(
        "/api/projects",
        json={
            "name": "Inline Fix Project",
            "settings": {
                "words_per_chapter": 4,
                "grid": {"mode": "custom", "rows": 5, "cols": 5, "min_density": 0.15},
            },
        },
    ).json()["id"]

    paste_text = (
        "Word,Clue\n"
        "cat,Small feline\n"
        "car,Four-wheeled vehicle\n"
        "planets,Orbiting bodies\n"
        "zzz,Sleeping sound\n"
    )
    staged = client.post(f"/api/projects/{pid}/imports/paste", json={"text": paste_text}).json()
    proj = client.post(f"/api/projects/{pid}/imports/{staged['id']}/accept").json()["project"]
    cid = proj["chapters"][0]["id"]

    # Initial generation in 5x5 -> PLANETS (7 chars) and ZZZ cannot fit
    gen = client.post(
        "/api/puzzles/generate",
        json={
            "collection_id": cid,
            "settings": {"rows": 5, "cols": 5, "seed": 1},
            "min_density": 0.15,
        },
    ).json()
    assert gen["needs_attention"] is True
    assert {u["answer"] for u in gen["unplaced"]} == {"PLANETS", "ZZZ"}

    # Action 1: new_seed (preserves all 4 words)
    act_seed = client.post(
        f"/api/projects/{pid}/chapters/{cid}/action",
        json={"action": "new_seed", "seed": 9},
    )
    assert act_seed.status_code == 200, act_seed.text
    seed_data = act_seed.json()
    assert seed_data["puzzle"]["winning_seed"] == 9
    assert len(seed_data["puzzle"]["entries"]) + len(seed_data["puzzle"]["unplaced"]) == 4

    # Action 2: larger_grid -> PLANETS now fits, only ZZZ remains unplaced
    act_grid = client.post(
        f"/api/projects/{pid}/chapters/{cid}/action",
        json={"action": "larger_grid", "rows": 9, "cols": 9},
    )
    assert act_grid.status_code == 200, act_grid.text
    grid_data = act_grid.json()
    assert grid_data["puzzle"]["rows"] == 9 and grid_data["puzzle"]["cols"] == 9
    assert [u["answer"] for u in grid_data["puzzle"]["unplaced"]] == ["ZZZ"]
    assert grid_data["chapter"]["status"] == "Needs attention"

    # Action 3: edit_word -> replace ZZZ with TAR (shares T/A/R) -> all 4 placed, chapter Ready
    act_edit = client.post(
        f"/api/projects/{pid}/chapters/{cid}/action",
        json={"action": "edit_word", "old_word": "ZZZ", "new_word": "tar", "clue": "Black road pitch"},
    )
    assert act_edit.status_code == 200, act_edit.text
    edit_data = act_edit.json()
    assert len(edit_data["puzzle"]["entries"]) == 4
    assert edit_data["puzzle"]["unplaced"] == []
    assert edit_data["chapter"]["status"] == "Ready"

    # Action 4: remove_word on another Needs attention chapter
    pid2 = client.post(
        "/api/projects",
        json={"name": "Remove Action Project", "settings": {"grid": {"min_density": 0.15}}},
    ).json()["id"]
    staged2 = client.post(
        f"/api/projects/{pid2}/imports/paste",
        json={"text": "Word,Clue\ncat,Feline\ncar,Vehicle\ntar,Road pitch\nzzz,Sleeping sound\n"},
    ).json()
    proj2 = client.post(f"/api/projects/{pid2}/imports/{staged2['id']}/accept").json()["project"]
    cid2 = proj2["chapters"][0]["id"]
    client.post("/api/puzzles/generate", json={"collection_id": cid2, "min_density": 0.15})
    act_rem = client.post(
        f"/api/projects/{pid2}/chapters/{cid2}/action",
        json={"action": "remove_word", "old_word": "ZZZ"},
    )
    assert act_rem.status_code == 200, act_rem.text
    rem_data = act_rem.json()
    assert len(rem_data["puzzle"]["entries"]) == 3
    assert rem_data["puzzle"]["unplaced"] == []
    assert rem_data["chapter"]["status"] == "Ready"


def test_hit_time_limit_exposed_in_job_report(db_setup, monkeypatch):
    client, SessionLocal = db_setup
    csv_bytes = "Word,Clue\ncat,Feline\ncar,Vehicle\ntar,Road pitch\n".encode("utf-8")
    imp = client.post("/api/imports", files={"file": ("tl.csv", csv_bytes, "text/csv")}).json()
    col_id = client.post(f"/api/imports/{imp['id']}/commit").json()["collections"][0]["id"]

    from app.crossword.services import bulk as bulk_mod

    orig_worker = bulk_mod._run_engine_worker

    def _timeout_worker(answers, settings_dict):
        out = orig_worker(answers, settings_dict)
        out["stats"]["hit_time_limit"] = True
        return out

    monkeypatch.setattr(bulk_mod, "_run_engine_worker", _timeout_worker)

    with SessionLocal() as db:
        job = create_bulk_generation_job(
            db,
            collection_ids=[col_id],
            auto_retry=False,
            generate_missing_clues=False,
            max_workers=1,
        )
        job_id = job.id

    execute_bulk_generation_job(
        job_id,
        SessionLocal,
        dictionary_provider=NullDictionaryProvider(),
        ai_provider=FakeAIProvider(),
        use_process_pool=False,
    )

    job_data = client.get(f"/api/jobs/{job_id}").json()
    assert job_data["result"]["hit_time_limit"] is True
    assert job_data["result"]["puzzles"][0]["hit_time_limit"] is True
    assert len(job_data["result"]["time_limit_warnings"]) == 1
    puz_detail = client.get(f"/api/puzzles/{job_data['result']['puzzles'][0]['puzzle_id']}").json()
    assert puz_detail["hit_time_limit"] is True


def test_plain_language_errors_and_raw_validator_checks_separation():
    from app.crossword.services.quality import build_plain_language_diagnostics

    raw_checks = {
        "entries_in_bounds": True,
        "entry_letters_match": True,
        "no_accidental_words": True,
        "entries_are_maximal_runs": False,
        "no_orphan_letters": True,
        "connected": True,
        "no_duplicate_answers": True,
        "numbering": True,
        "every_word_accounted_for": True,
    }
    diag = build_plain_language_diagnostics(
        validation={"valid": False, "checks": raw_checks, "errors": ["entries_are_maximal_runs failed"]},
        unplaced=[
            {"answer": "X", "reason": "blocked"},
            {"answer": "Y", "reason": "blocked"},
            {"answer": "Z", "reason": "blocked"},
        ],
        quality={
            "density": 0.12,
            "min_density": 0.25,
            "density_ok": False,
            "crossing_count": 1,
            "min_crossings": 1,
            "crossings_ok": True,
            "meets_threshold": False,
            "status": "Needs attention",
        },
        stats={"hit_time_limit": True},
    )

    assert "3 words couldn't be placed: X, Y, Z. Try a larger grid or a new seed." in diag["messages"]
    assert diag["hit_time_limit"] is True
    combined_plain = diag["headline"] + " " + " ".join(diag["messages"])
    for raw_name in raw_checks:
        assert raw_name not in combined_plain
    assert diag["raw_checks"] == raw_checks
