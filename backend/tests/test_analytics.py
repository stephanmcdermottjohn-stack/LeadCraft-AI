"""P1 #4: website analytics - cookie-free events, honest rates, tenant scoping."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'analytics.db'}")
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
        json={"business_name": "Gulberg Salon", "email": "stats@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "stats-salon"}, headers=headers)
    return headers


def event(client, session_id, name, slug="stats-salon", path="/l/stats-salon"):
    return client.post(
        f"/api/public/landing/{slug}/events",
        json={"session_id": session_id, "event": name, "path": path, "referrer": "https://google.com/search?q=secret"},
    )


def test_public_events_and_summary(client, env):
    headers = env
    assert event(client, "sess-aaaa1111", "page_view").status_code == 204
    assert event(client, "sess-aaaa1111", "form_start").status_code == 204
    assert event(client, "sess-aaaa1111", "submit").status_code == 204
    assert event(client, "sess-bbbb2222", "page_view").status_code == 204
    # Unknown slug / malformed payloads: silent 204, nothing stored.
    assert event(client, "sess-cccc3333", "page_view", slug="nope-salon").status_code == 204
    assert event(client, "x", "page_view").status_code == 204
    assert event(client, "sess-dddd4444", "click").status_code == 204

    body = client.get("/api/analytics/summary", headers=headers).json()
    assert body["events_total"] == 4
    assert body["sessions_total"] == 2
    assert body["funnel"] == {"page_view_sessions": 2, "form_start_sessions": 1, "submit_sessions": 1}
    # Below 30 sessions: honest null rates, never 0%.
    assert body["rates_known"] is False
    assert body["form_start_rate_pct"] is None and body["submit_rate_pct"] is None
    assert any("too early" in n for n in body["notes"])
    # No PII stored: referrer host only, query stripped from the path.
    from app import db as db_module
    from app.models import AnalyticsEvent

    db = db_module.SessionLocal()
    rows = db.query(AnalyticsEvent).all()
    db.close()
    assert rows and all(r.referrer == "google.com" for r in rows)
    assert all("?" not in r.path for r in rows)


def test_rates_known_after_enough_sessions(client, env):
    headers = env
    for i in range(30):
        sid = f"sess-rate-{i:04d}"
        event(client, sid, "page_view")
        if i < 15:
            event(client, sid, "form_start")
        if i < 5:
            event(client, sid, "submit")
    body = client.get("/api/analytics/summary?days=7", headers=headers).json()
    assert body["sessions_total"] == 30
    assert body["rates_known"] is True
    assert body["form_start_rate_pct"] == 50.0
    assert body["submit_rate_pct"] == 16.7
    assert body["window_days"] == 7
    assert len(body["daily"]) == 7


def test_summary_requires_auth_and_is_tenant_scoped(client, env):
    headers = env
    event(client, "sess-tenant1", "page_view")
    assert client.get("/api/analytics/summary").status_code == 401
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "statsother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    body = client.get("/api/analytics/summary", headers=oh).json()
    assert body["events_total"] == 0 and body["sessions_total"] == 0
    assert any("No analytics events" in n for n in body["notes"])


def test_summary_counts_only_own_leads(client, env):
    headers = env
    client.post(
        "/api/leads/capture",
        json={"slug": "stats-salon", "name": "Ayesha", "phone": "03001112222", "consent": True},
    )
    body = client.get("/api/analytics/summary", headers=headers).json()
    assert body["leads_captured"] == 1
