"""Phase L (P0): lifecycle engine + stage history + attribution. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'lifecycle.db'}")
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
def owner_headers(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "owner@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    res = client.patch(
        "/api/settings",
        json={"niche": "bridal makeup", "landing_slug": "gulberg-salon"},
        headers=headers,
    )
    assert res.status_code == 200
    return headers


def _capture(client, **overrides):
    body = {
        "slug": "gulberg-salon",
        "name": "Ayesha Khan",
        "phone": "03001234567",
        "consent": True,
        "campaign": "december-bridal",
        "utm_source": "instagram",
        "utm_medium": "story",
        "utm_content": "carousel-a",
        "utm_term": "bridal",
    }
    body.update(overrides)
    return client.post("/api/leads/capture", json=body)


# --- attribution ----------------------------------------------------------------

def test_capture_stores_attribution(client, owner_headers):
    res = _capture(client)
    assert res.status_code == 201, res.text
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead["campaign"] == "december-bridal"
    assert lead["utm_source"] == "instagram"
    assert lead["utm_medium"] == "story"
    assert lead["utm_content"] == "carousel-a"
    assert lead["utm_term"] == "bridal"
    # No attribution params -> empty strings, not junk.
    _capture(client, name="Plain", email="plain@leadcrafttest.com", campaign="", utm_source="",
             utm_medium="", utm_content="", utm_term="")
    lead2 = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead2["campaign"] == "" and lead2["utm_source"] == ""


# --- lifecycle stages ------------------------------------------------------------

def test_new_lead_starts_at_capture_with_next_action(client, owner_headers):
    _capture(client, campaign="")
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead["lifecycle_stage"] == "capture"
    assert lead["next_action"]  # default recommendation present
    history = client.get(f"/api/leads/{lead['id']}/stage-history", headers=owner_headers).json()["history"]
    assert [(h["from_stage"], h["to_stage"]) for h in history] == [("", "capture")]


def test_stage_transition_records_history(client, owner_headers):
    _capture(client, campaign="")
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]

    res = client.patch(
        f"/api/leads/{lead['id']}/stage",
        json={"stage": "qualify", "note": "ICP fit looks strong", "assigned_to": "Sohaib"},
        headers=owner_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()["lead"]
    assert body["lifecycle_stage"] == "qualify"
    assert body["assigned_to"] == "Sohaib"
    # Suggested next action follows the new stage (was unset).
    assert "BANT" in body["next_action"]

    res = client.patch(
        f"/api/leads/{lead['id']}/stage",
        json={"stage": "nurture", "next_action": "Send catalogue on Thursday", "next_action_at": "2026-12-01T10:00:00Z"},
        headers=owner_headers,
    )
    assert res.status_code == 200
    body = res.json()["lead"]
    assert body["next_action"] == "Send catalogue on Thursday"
    assert body["next_action_at"] is not None

    history = client.get(f"/api/leads/{lead['id']}/stage-history", headers=owner_headers).json()["history"]
    stages = [(h["from_stage"], h["to_stage"]) for h in history]
    assert ("capture", "qualify") in stages
    assert ("qualify", "nurture") in stages
    assert history[0]["to_stage"] == "nurture"  # newest first
    assert any(h["note"] == "ICP fit looks strong" for h in history)


def test_stage_invalid_and_cross_tenant(client, owner_headers):
    _capture(client, campaign="")
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert client.patch(f"/api/leads/{lead['id']}/stage", json={"stage": "chaos"}, headers=owner_headers).status_code == 400

    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "other-lc@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.patch(f"/api/leads/{lead['id']}/stage", json={"stage": "qualify"}, headers=oh).status_code == 404
    assert client.get(f"/api/leads/{lead['id']}/stage-history", headers=oh).status_code == 404


def test_converted_status_bridges_to_convert_stage(client, owner_headers):
    _capture(client, campaign="")
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    res = client.patch(f"/api/leads/{lead['id']}/status", json={"status": "converted"}, headers=owner_headers)
    assert res.status_code == 200
    body = res.json()["lead"]
    assert body["status"] == "converted"
    assert body["lifecycle_stage"] == "convert"
    history = client.get(f"/api/leads/{lead['id']}/stage-history", headers=owner_headers).json()["history"]
    assert ("capture", "convert") in [(h["from_stage"], h["to_stage"]) for h in history]
    # Other statuses leave the stage alone.
    client.patch(f"/api/leads/{lead['id']}/status", json={"status": "contacted"}, headers=owner_headers)
    assert client.get("/api/leads", headers=owner_headers).json()["leads"][0]["lifecycle_stage"] == "convert"
