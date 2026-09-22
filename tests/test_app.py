"""API tests — run against SQLite with mock AI (no external services)."""
import io

import pytest
from PIL import Image


def make_jpeg(color=(20, 120, 60)) -> bytes:
    img = Image.new("RGB", (64, 64), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    # Re-import the app fresh with these settings.
    import importlib

    import app.config
    import app.db
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.main)
    app.main.init_db()
    from fastapi.testclient import TestClient

    return TestClient(app.main.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_submit_creates_pending(client):
    r = client.post(
        "/api/v1/observations",
        data={"text_description": "Plastic bottles and trash along the bank"},
        files={"photo": ("t.jpg", make_jpeg(), "image/jpeg")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "trash_or_debris" in body["ai_indicators"]
    assert body["ai_confidence"] > 0
    assert body["ai_reasoning"]


def test_reject_non_image(client):
    r = client.post(
        "/api/v1/observations",
        data={"text_description": "test"},
        files={"photo": ("t.txt", b"not an image at all" * 10, "image/jpeg")},
    )
    assert r.status_code == 400


def test_queue_requires_auth(client):
    assert client.get("/api/v1/queue").status_code == 401
    assert client.post("/api/v1/observations/1/approve").status_code in (401, 403)


def test_full_review_flow(client):
    from app.auth import verify_credentials

    assert verify_credentials("reviewer", "reviewer-dev-password")

    login = client.post(
        "/api/v1/auth/login",
        data={"username": "reviewer", "password": "reviewer-dev-password"},
    )
    assert login.status_code == 200, login.text
    csrf = login.cookies.get("riparia_csrf", "")
    assert csrf, "login must set the riparia_csrf cookie"
    client.cookies.update(login.cookies)

    r = client.post(
        "/api/v1/observations",
        data={"text_description": "Foam on the water near the outfall pipe"},
        files={"photo": ("t.jpg", make_jpeg((90, 90, 200)), "image/jpeg")},
    )
    obs = r.json()

    q = client.get("/api/v1/queue")
    assert q.status_code == 200
    assert any(item["id"] == obs["id"] for item in q.json()["items"])

    rej = client.post(
        f"/api/v1/observations/{obs['id']}/reject",
        headers={"X-CSRF-Token": csrf},
    )
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"
    assert rej.json()["fhir_id"] is None
