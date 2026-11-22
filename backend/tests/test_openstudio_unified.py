"""Smoke tests verifying Openstudio unifies Word Search and Crossword APIs."""
from fastapi.testclient import TestClient

from app.main import app


def test_openstudio_unified_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "ok"
        assert body["app"] == "Openstudio"
        assert set(body["studios"]) == {"wordsearch", "crossword"}


def test_wordsearch_and_crossword_endpoints_coexist():
    with TestClient(app) as client:
        ws = client.get("/api/wordsearch/health")
        assert ws.status_code == 200
        assert ws.json()["ok"] is True

        cw = client.get("/api/projects")
        assert cw.status_code == 200
        assert isinstance(cw.json(), list)
