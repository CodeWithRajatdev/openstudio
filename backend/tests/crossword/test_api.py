from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_generate_endpoint_reports_everything():
    body = {"words": ["apple", "planet", "elephant", "APPLE", "r2d2", "courage"], "settings": {"time_limit_s": 10}}
    data = client.post("/api/engine/generate", json=body).json()
    assert data["validation"]["valid"] is True
    assert len(data["duplicate_inputs"]) == 1
    assert len(data["rejected_inputs"]) == 1
    assert len(data["entries"]) + len(data["unplaced"]) == 4
