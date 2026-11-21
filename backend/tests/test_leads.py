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
        "show_property_fields": False,
        "business_type": "",
        "extra_fields": [],
        # P3 #2 white-label defaults (presentation only, empty = not set).
        "brand_name": "",
        "logo_url": "",
        "primary_color": "",
        "support_email": "",
        "footer_text": "",
        "hide_platform_brand": False,
        # P1 A/B: no variants exist -> control served, no override payload.
        "ab_variant": "control",
        "variant": None,
        # P5 #1: booking is off by default (public subset only).
        "booking": {
            "enabled": False,
            "slot_minutes": 30,
            "start": "10:00",
            "end": "18:00",
            "days": [],
            "timezone": "Asia/Karachi",
            "services": [],
            "lead_minutes": 60,
            "note": "",
            "max_days_ahead": 60,
        },
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


# --- property module (Phase 3B) -----------------------------------------------

def test_capture_stores_property_fields_in_metadata(client, owner_headers):
    res = _capture(client, deal_type="Buy", property_type="5 Marla house", budget="2.5 crore")
    assert res.status_code == 201, res.text
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    md = lead["metadata"]
    assert md == {"deal_type": "buy", "property_type": "5 Marla house", "budget": "2.5 crore"}
    # No property fields -> empty metadata (no junk keys).
    res = _capture(client, name="Plain Visitor", email="plain@leadcrafttest.com", phone="")
    lead2 = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead2["metadata"] == {}


def test_show_property_fields_toggle_roundtrip(client, owner_headers):
    res = client.patch("/api/settings", json={"show_property_fields": True}, headers=owner_headers)
    assert res.status_code == 200
    assert res.json()["settings"]["show_property_fields"] is True
    body = client.get("/api/public/landing/gulberg-salon").json()
    assert body["show_property_fields"] is True
    # Omitted keeps it on.
    res = client.patch("/api/settings", json={}, headers=owner_headers)
    assert res.json()["settings"]["show_property_fields"] is True


# --- search / filter / export (Phase 3C) ---------------------------------------

def test_leads_search_and_filters(client, owner_headers):
    _capture(client, name="Ayesha Khan", area="Gulberg", intent_notes="bridal makeup")
    _capture(client, name="Bilal Ahmed", area="Model Town", intent_notes="party makeup",
             deal_type="buy", property_type="house", budget="2 crore")
    _capture(client, name="Sana Malik", email="sana@leadcrafttest.com", phone="", intent_notes="salon booking")

    by_name = client.get("/api/leads", params={"q": "bilal"}, headers=owner_headers).json()["leads"]
    assert [l["name"] for l in by_name] == ["Bilal Ahmed"]
    by_notes = client.get("/api/leads", params={"q": "bridal"}, headers=owner_headers).json()["leads"]
    assert len(by_notes) == 1
    assert client.get("/api/leads", params={"status": "new"}, headers=owner_headers).json()["leads"].__len__() == 3
    client.patch("/api/leads/1/status", json={"status": "contacted"}, headers=owner_headers)
    filtered = client.get("/api/leads", params={"status": "contacted"}, headers=owner_headers).json()["leads"]
    assert len(filtered) == 1
    assert client.get("/api/leads", params={"status": "bogus"}, headers=owner_headers).status_code == 400
    assert client.get("/api/leads", params={"source": "bogus"}, headers=owner_headers).status_code == 400


def test_leads_csv_export(client, owner_headers):
    _capture(client, deal_type="rent", budget="1 lakh")
    res = client.get("/api/leads/export.csv", headers=owner_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    text = res.text
    assert "id,created_at,source,status,name,phone,email,area" in text
    assert "Ayesha Khan" in text
    assert "rent" in text
    # Another user gets only their (empty) export.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "csvother@leadcrafttest.com", "password": "supersecret1"},
    )
    res2 = client.get("/api/leads/export.csv", headers={"Authorization": f"Bearer {other.json()['token']}"})
    assert "Ayesha Khan" not in res2.text


# --- lead notes (Phase 3C) ------------------------------------------------------

def test_lead_notes_add_list_and_isolation(client, owner_headers):
    _capture(client)
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    res = client.post(f"/api/leads/{lead['id']}/notes", json={"body": "Called, wants December slot."}, headers=owner_headers)
    assert res.status_code == 201
    res = client.post(f"/api/leads/{lead['id']}/notes", json={"body": "Sent WhatsApp catalogue."}, headers=owner_headers)
    assert res.status_code == 201
    notes = client.get(f"/api/leads/{lead['id']}/notes", headers=owner_headers).json()["notes"]
    assert len(notes) == 2
    assert notes[0]["body"] == "Sent WhatsApp catalogue."  # newest first

    # Empty note rejected.
    assert client.post(f"/api/leads/{lead['id']}/notes", json={"body": "  "}, headers=owner_headers).status_code == 422

    # Another user cannot read or write this lead's notes.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "noteother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get(f"/api/leads/{lead['id']}/notes", headers=oh).status_code == 404
    assert client.post(f"/api/leads/{lead['id']}/notes", json={"body": "hijack"}, headers=oh).status_code == 404


# --- business templates (Phase 3D) ---------------------------------------------

def test_business_type_validation_and_roundtrip(client, owner_headers):
    res = client.patch("/api/settings", json={"business_type": "hospitality"}, headers=owner_headers)
    assert res.status_code == 200
    assert res.json()["settings"]["business_type"] == "hospitality"
    assert client.patch("/api/settings", json={"business_type": "nonsense"}, headers=owner_headers).status_code == 400
    assert client.patch("/api/settings", json={"business_type": ""}, headers=owner_headers).status_code == 200
    assert client.patch("/api/settings", json={"business_type": "property"}, headers=owner_headers).status_code == 200


def test_landing_extras_follow_template_and_toggle(client, owner_headers):
    client.patch("/api/settings", json={"business_type": "property", "show_property_fields": True}, headers=owner_headers)
    body = client.get("/api/public/landing/gulberg-salon").json()
    keys = [e["key"] for e in body["extra_fields"]]
    assert keys == ["deal_type", "property_type", "budget"]
    assert body["extra_fields"][0]["options"] == ["buy", "rent", "sell"]

    # Hospitality template swaps the field set.
    client.patch("/api/settings", json={"business_type": "hospitality"}, headers=owner_headers)
    body = client.get("/api/public/landing/gulberg-salon").json()
    keys = [e["key"] for e in body["extra_fields"]]
    assert keys == ["room_type", "guests", "stay_dates", "budget"]

    # Toggle off -> no extras.
    client.patch("/api/settings", json={"show_property_fields": False}, headers=owner_headers)
    body = client.get("/api/public/landing/gulberg-salon").json()
    assert body["extra_fields"] == []
    client.patch("/api/settings", json={"show_property_fields": True}, headers=owner_headers)


def test_capture_generic_extra_whitelisted_and_stored(client, owner_headers):
    client.patch(
        "/api/settings",
        json={"business_type": "hospitality", "show_property_fields": True},
        headers=owner_headers,
    )
    _capture(client, extra={"room_type": "suite", "guests": "3", "stay_dates": "Dec 20-22"})
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead["metadata"] == {"room_type": "suite", "guests": "3", "stay_dates": "Dec 20-22"}

    # Unknown / not-enabled keys are silently dropped (no junk in metadata).
    _capture(client, name="Bot Keys", email="botkeys@leadcrafttest.com", phone="",
             extra={"room_type": "deluxe", "evil_key": "x", "budget": "10k"})
    lead = client.get("/api/leads", headers=owner_headers).json()["leads"][0]
    assert lead["metadata"] == {"room_type": "deluxe", "budget": "10k"}


# --- manual platform-export import (Meta/Google) -------------------------------

def test_lead_import_requires_platform_source_and_consent(client, owner_headers):
    rows = [{"name": "R1", "phone": "03001112233"}, {"name": "R2", "email": "r2@leadcrafttest.com"}]
    res = client.post("/api/leads/import", json={"source": "landing_page", "consent": True, "rows": rows}, headers=owner_headers)
    assert res.status_code == 400
    res = client.post("/api/leads/import", json={"source": "meta_lead_ad", "consent": False, "rows": rows}, headers=owner_headers)
    assert res.status_code == 400
    res = client.post("/api/leads/import", json={"source": "meta_lead_ad", "consent": True, "rows": []}, headers=owner_headers)
    assert res.status_code == 400


def test_lead_import_creates_leads_skips_malformed(client, owner_headers):
    rows = [
        {"name": "Farhan Ali", "phone": "03214445566", "area": "Johar Town", "notes": "Renovation quote"},
        {"name": "", "phone": "03009998877"},            # no name -> skipped
        {"name": "No Contact", "phone": "", "email": ""},  # no phone/email -> skipped
        {"name": "Zoya Butt", "email": "zoya@leadcrafttest.com", "notes": "Bridal package"},
    ]
    res = client.post("/api/leads/import", json={"source": "google_lead_form", "consent": True, "rows": rows}, headers=owner_headers)
    assert res.status_code == 201, res.text
    assert res.json() == {"imported": 2, "skipped": 2}

    leads = client.get("/api/leads", headers=owner_headers).json()["leads"]
    imported = [l for l in leads if l["source"] == "google_lead_form"]
    assert {l["name"] for l in imported} == {"Farhan Ali", "Zoya Butt"}
    assert all(l["consent_timestamp"] for l in imported)

    # Cross-user isolation: another user's import doesn't leak.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "impother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/leads", headers=oh).json()["leads"] == []


# --- admin overview (Phase 3D) -------------------------------------------------

def test_admin_overview_requires_admin(client, owner_headers):
    assert client.get("/api/admin/overview", headers=owner_headers).status_code == 403


def test_admin_overview_stats(client, owner_headers):
    _capture(client)
    _capture(client, name="Second Lead", email="second@leadcrafttest.com", phone="")

    from app.models import User as UserModel
    user = client.get("/api/auth/me", headers=owner_headers).json()["user"]
    # Promote via the session's engine (test fixture DB is per-module).
    from app.db import SessionLocal
    db = SessionLocal()
    db_user = db.get(UserModel, user["id"])
    db_user.is_admin = True
    db.commit()
    db.close()

    body = client.get("/api/admin/overview", headers=owner_headers).json()
    assert body["total_users"] >= 1
    assert body["total_leads"] >= 2
    assert body["leads_by_status"].get("new", 0) >= 2
    assert body["leads_by_source"].get("landing_page", 0) >= 2
    assert any(u["email"] == "owner@leadcrafttest.com" for u in body["recent_users"])
    assert all("business_name" in u and "email" in u and "lead_count" in u for u in body["recent_users"])
