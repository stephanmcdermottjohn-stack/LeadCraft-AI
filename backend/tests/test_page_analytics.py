"""P7 #2: custom page analytics + per-page lead attribution. Zero network.

Covers the new Lead.landing_page_slug column (capture + filter + CSV), the
published-only public event endpoint (path is forced server-side), the grouped
list stats, and the per-page analytics summary with tenant isolation.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pageanalytics.db'}")
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


def register(client, email="analytics@leadcrafttest.com", business_name="Gulberg Salon", slug=None):
    res = client.post(
        "/api/auth/register",
        json={"business_name": business_name, "email": email, "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        assert client.patch("/api/settings", json={"landing_slug": slug}, headers=headers).status_code == 200
    return headers


def make_page(client, headers, slug="eid-offer", published=True):
    res = client.post(
        "/api/pages",
        json={
            "slug": slug,
            "title": "Eid offer",
            "is_published": published,
            "blocks": [{"type": "hero", "heading": "Eid is here"}],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["page"]


def capture(client, payload):
    return client.post("/api/leads/capture", json=payload)


def event(client, slug, event_name="page_view", session="session-abc123", path=None):
    body = {"session_id": session, "event": event_name}
    if path is not None:
        body["path"] = path
    return client.post(f"/api/public/pages/{slug}/events", json=body)


def test_capture_sets_page_slug_and_filter(client):
    headers = register(client, slug="analytics-salon")
    make_page(client, headers, slug="eid-offer")

    # Custom page capture records the slug on the lead itself (not only JSON).
    assert capture(client, {
        "page_slug": "eid-offer", "name": "Ayesha", "phone": "03001234567", "consent": True,
    }).status_code == 201
    # Template landing capture stays null.
    assert capture(client, {
        "slug": "analytics-salon", "name": "Bilal", "email": "bilal@example.com", "consent": True,
    }).status_code == 201

    leads = client.get("/api/leads", headers=headers).json()["leads"]
    by_name = {l["name"]: l for l in leads}
    assert by_name["Ayesha"]["landing_page_slug"] == "eid-offer"
    assert by_name["Bilal"]["landing_page_slug"] is None

    filtered = client.get("/api/leads", params={"page": "eid-offer"}, headers=headers).json()["leads"]
    assert [l["name"] for l in filtered] == ["Ayesha"]
    assert client.get("/api/leads", params={"page": "other-page"}, headers=headers).json()["leads"] == []

    csv_body = client.get("/api/leads/export.csv", headers=headers).text
    assert "landing_page_slug" in csv_body.splitlines()[0]
    assert "eid-offer" in csv_body

    # Tenant isolation: another workspace only sees its own leads.
    other = register(client, email="other@analytics.com", business_name="Other", slug="other-salon")
    assert client.get("/api/leads", params={"page": "eid-offer"}, headers=other).json()["leads"] == []


def test_public_events_published_only_and_path_is_forced(client):
    headers = register(client, slug="events-salon")
    page = make_page(client, headers, slug="events-offer", published=False)

    # Draft: accepted silently but never stored.
    assert event(client, "events-offer").status_code == 204
    assert client.get("/api/pages", headers=headers).json()["pages"][0]["stats"]["views"] == 0
    # Unknown page and malformed payload are silent no-ops.
    assert event(client, "unknown-page").status_code == 204
    assert client.post(
        "/api/public/pages/events-offer/events", json={"session_id": "short", "event": "page_view"}
    ).status_code == 204
    assert client.post(
        "/api/public/pages/events-offer/events", json={"session_id": "session-abc123", "event": "nope"}
    ).status_code == 204

    # Publish, then record traffic. A spoofed /l/ path is overwritten.
    assert client.patch(
        f"/api/pages/{page['id']}", json={"is_published": True}, headers=headers
    ).status_code == 200
    assert event(client, "events-offer", session="session-aaa111").status_code == 204
    assert event(client, "events-offer", session="session-bbb222", path="/l/events-salon").status_code == 204
    assert event(client, "events-offer", event_name="form_start", session="session-aaa111").status_code == 204

    stats = client.get("/api/pages", headers=headers).json()["pages"][0]["stats"]
    assert stats["window_days"] == 30
    assert stats["views"] == 2  # forced /p/ path, both sessions counted
    assert stats["leads"] == 0
    assert stats["conversion_pct"] == 0.0  # raw fact...
    assert stats["conversion_known"] is False  # ...but too early to judge (needs 30 views)


def test_page_stats_and_analytics_detail(client):
    headers = register(client, slug="detail-salon")
    page = make_page(client, headers, slug="detail-offer")

    for session in ("session-aaa111", "session-bbb222", "session-ccc333"):
        assert event(client, "detail-offer", session=session).status_code == 204
    assert event(client, "detail-offer", event_name="submit", session="session-aaa111").status_code == 204
    assert capture(client, {
        "page_slug": "detail-offer", "name": "Sara", "phone": "0300", "consent": True,
    }).status_code == 201

    stats = client.get("/api/pages", headers=headers).json()["pages"][0]["stats"]
    assert stats["views"] == 3
    assert stats["leads"] == 1
    assert stats["conversion_pct"] == 33.3

    detail = client.get(f"/api/pages/{page['id']}/analytics", headers=headers).json()
    assert detail["page"]["slug"] == "detail-offer"
    assert detail["funnel"]["page_view_sessions"] == 3
    assert detail["funnel"]["form_start_sessions"] == 0
    assert detail["event_counts"]["submit"] == 1
    assert detail["leads_captured"] == 1
    assert detail["rates_known"] is False
    assert any("too early" in n for n in detail["notes"])
    assert len(detail["daily"]) == 14

    # Template-page leads never inflate a custom page's numbers.
    assert capture(client, {
        "slug": "detail-salon", "name": "Template", "phone": "0301", "consent": True,
    }).status_code == 201
    detail2 = client.get(f"/api/pages/{page['id']}/analytics", headers=headers).json()
    assert detail2["leads_captured"] == 1

    # Tenant isolation.
    other = register(client, email="other@detail.com", business_name="Other", slug="other-detail")
    assert client.get(f"/api/pages/{page['id']}/analytics", headers=other).status_code == 404
