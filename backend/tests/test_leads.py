"""Phase 3 gate: consent-first lead capture, public landing config, slug
management, and user-scoped lead management. Zero network — pure API tests.
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'leads.db'}")
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
    """Business owner with a landing slug configured."""
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "owner@leadcrafttest.com", "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    res = client.patch(
        "/api/settings",
        json={"niche": "bridal makeup", "target_area": "Gulberg Lahore", "brand_voice": "warm", "landing_slug": "gulberg-salon"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return headers


def _capture(client, **overrides):
    body = {
        "slug": "gulberg-salon",
        "name": "Ayesha Khan",
        "phone": "03001234567",
        "email": "",
        "area": "Gulberg",
        "intent_notes": "Bridal makeup for December wedding",
        "consent": True,
    }
    body.update(overrides)
    return client.post("/api/leads/capture", json=body)


# --- capture ------------------------------------------------------------------

def test_capture_creates_consented_lead(client, owner_headers):
    before = datetime.datetime.now(datetime.timezone.utc)
    res = _capture(client)
    assert res.status_code == 201, res.text

    leads = client.get("/api/leads", headers=owner_headers).json()["leads"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["source"] == "landing_page"
    assert lead["name"] == "Ayesha Khan"
    assert lead["status"] == "new"
    # Consent timestamp recorded SERVER-SIDE, not trusted from the client.
    ts = datetime.datetime.fromisoformat(lead["consent_timestamp"])
    if ts.tzinfo is None:  # SQLite returns naive datetimes
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    assert ts >= before
    # The capturer (anonymous) must not see or need auth for the dashboard
    # data; the lead belongs to the slug owner only.
    assert client.get("/api/leads").status_code == 401


def test_capture_requires_consent(client, owner_headers):
    res = _capture(client, consent=False)
    assert res.status_code == 400
    assert "consent" in res.json()["detail"].lower()
    assert client.get("/api/leads", headers=owner_headers).json()["leads"] == []


def test_capture_honeypot_rejects_bots(client, owner_headers):
    res = _capture(client, company="SEO Bot Inc")
    assert res.status_code == 400
    assert client.get("/api/leads", headers=owner_headers).json()["leads"] == []


def test_capture_requires_phone_or_email(client, owner_headers):
    res = _capture(client, phone="", email="")
    assert res.status_code == 400


def test_capture_unknown_slug_404(client, owner_headers):
    res = _capture(client, slug="no-such-business")
    assert res.status_code == 404


def test_capture_email_normalized_lowercase(client, owner_headers):
    res = _capture(client, phone="", email="Ayesha.Khan@Example.com")
    assert res.status_code == 201
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead["email"] == "ayesha.khan@example.com"


# --- public landing config ----------------------------------------------------

def test_public_landing_config_display_fields_only(client, owner_headers):
    res = client.get("/api/public/landing/gulberg-salon")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "slug": "gulberg-salon",
        "business_name": "Gulberg Salon",
        "niche": "bridal makeup",
        "target_area": "Gulberg Lahore",
    }
    # No credentials, no other fields leak.
    assert "brand_voice" not in body
    assert "landing_slug" not in body


def test_public_landing_unknown_slug_404(client):
    assert client.get("/api/public/landing/unknown-slug").status_code == 404


# --- lead management (user-scoped) --------------------------------------------

def test_leads_list_is_user_scoped(client, owner_headers):
    _capture(client)
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other Biz", "email": "other@leadcrafttest.com", "password": "supersecret1"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/leads", headers=other_headers).json()["leads"] == []
    assert len(client.get("/api/leads", headers=owner_headers).json()["leads"]) == 1


def test_lead_status_update_and_validation(client, owner_headers):
    assert _capture(client).status_code == 201
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    res = client.patch(f"/api/leads/{lead['id']}/status", json={"status": "contacted"}, headers=owner_headers)
    assert res.status_code == 200
    assert res.json()["lead"]["status"] == "contacted"

    assert client.patch(f"/api/leads/{lead['id']}/status", json={"status": "hacked"}, headers=owner_headers).status_code == 400
    # Another owner cannot touch someone else's lead.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other Biz", "email": "other2@leadcrafttest.com", "password": "supersecret1"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.patch(f"/api/leads/{lead['id']}/status", json={"status": "new"}, headers=other_headers).status_code == 404


# --- slug management -----------------------------------------------------------

def test_slug_auto_derives_from_business_name(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Sana Properties", "email": "sana@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    body = client.patch("/api/settings", json={"landing_slug": "auto"}, headers=headers)
    assert body.status_code == 200
    assert body.json()["settings"]["landing_slug"] == "sana-properties"


def test_slug_auto_suffixes_on_conflict(client, owner_headers):
    # gulberg-salon exists; a second "Gulberg Salon" gets -2.
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "gulberg2@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    body = client.patch("/api/settings", json={"landing_slug": "auto"}, headers=headers)
    assert body.status_code == 200
    assert body.json()["settings"]["landing_slug"] == "gulberg-salon-2"


def test_slug_explicit_conflict_409_and_invalid_400(client, owner_headers):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Third Biz", "email": "third@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    assert client.patch("/api/settings", json={"landing_slug": "gulberg-salon"}, headers=headers).status_code == 409
    assert client.patch("/api/settings", json={"landing_slug": "Bad Slug!"}, headers=headers).status_code == 400
    assert client.patch("/api/settings", json={"landing_slug": "api"}, headers=headers).status_code == 400
    # Empty / omitted keeps the existing (unset) slug.
    body = client.patch("/api/settings", json={"landing_slug": ""}, headers=headers)
    assert body.status_code == 200
    assert body.json()["settings"]["landing_slug"] is None
