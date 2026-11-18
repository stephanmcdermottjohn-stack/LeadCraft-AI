"""P0 #6: unified per-lead activity timeline. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'timeline.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from app import config, db

    config.get_settings.cache_clear()
    db.engine = db.create_engine_for_current_settings()
    db.SessionLocal = db.sessionmaker(bind=db.engine, autoflush=False, expire_on_commit=False, future=True)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def env(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "tl@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "tl-salon"}, headers=headers)
    cap = client.post(
        "/api/leads/capture", json={"slug": "tl-salon", "name": "Ayesha", "phone": "03001234567", "consent": True}
    )
    return headers, cap.json()["lead"]["id"]


def _types(client, headers, lid):
    return [e["type"] for e in client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]]


def test_timeline_merges_all_sources(client, env):
    headers, lid = env
    client.post(f"/api/leads/{lid}/notes", json={"body": "Called, interested"}, headers=headers)
    client.patch(f"/api/leads/{lid}/status", json={"status": "contacted"}, headers=headers)
    client.patch(f"/api/leads/{lid}/stage", json={"stage": "qualify"}, headers=headers)
    client.patch(f"/api/leads/{lid}/qualification", json={"budget": "150000"}, headers=headers)
    tl = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    types = [e["type"] for e in tl]
    assert "note" in types and "stage" in types
    assert "status_changed" in types and "qualification_updated" in types
    # Stage history also holds the capture row.
    stage_texts = [e["text"] for e in tl if e["type"] == "stage"]
    assert any("capture" in t for t in stage_texts) and any("qualify" in t for t in stage_texts)
    assert any("150000" in e["text"] for e in tl if e["type"] == "qualification_updated")


def test_no_duplicate_status_log(client, env):
    headers, lid = env
    client.patch(f"/api/leads/{lid}/status", json={"status": "contacted"}, headers=headers)
    client.patch(f"/api/leads/{lid}/status", json={"status": "contacted"}, headers=headers)  # same value
    status_events = [e for e in client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
                     if e["type"] == "status_changed"]
    assert len(status_events) == 1
    assert "new -> contacted" in status_events[0]["text"].replace("→", "->")


def test_newest_first(client, env):
    headers, lid = env
    client.post(f"/api/leads/{lid}/notes", json={"body": "first note"}, headers=headers)
    client.patch(f"/api/leads/{lid}/status", json={"status": "contacted"}, headers=headers)
    tl = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    stamps = [e["at"] for e in tl]
    assert stamps == sorted(stamps, reverse=True)
    # Capture stage row exists and sorts with the rest.
    assert len(tl) >= 3


def test_tenant_isolation_and_empty(client, env):
    headers, lid = env
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "tlother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get(f"/api/leads/{lid}/timeline", headers=oh).status_code == 404
    # Fresh lead: timeline has at least the capture stage row.
    own = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    assert any(e["type"] == "stage" and "capture" in e["text"] for e in own)
