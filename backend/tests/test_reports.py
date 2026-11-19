"""P1 #5: funnel + campaign reports - honest reached/current split, rates gated."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'reports.db'}")
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


def register(client, email="reports@leadcrafttest.com"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "reports-salon"}, headers=headers)
    return headers


def capture(client, name, campaign="", utm_source=""):
    res = client.post(
        "/api/leads/capture",
        json={
            "slug": "reports-salon",
            "name": name,
            "phone": "03001112222",
            "consent": True,
            "campaign": campaign,
            "utm_source": utm_source,
        },
    )
    return res.json()["lead"]["id"]


def test_funnel_reached_and_current(client):
    headers = register(client)
    ids = [capture(client, f"Lead {i}", campaign="Eid promo" if i < 6 else "", utm_source="instagram" if i % 2 else "") for i in range(12)]
    # Move 5 leads to qualify, 3 of those to convert.
    for lid in ids[:5]:
        assert client.patch(f"/api/leads/{lid}/stage", json={"stage": "qualify"}, headers=headers).status_code == 200
    for lid in ids[:3]:
        assert client.patch(f"/api/leads/{lid}/stage", json={"stage": "convert"}, headers=headers).status_code == 200

    body = client.get("/api/reports/funnel?days=30", headers=headers).json()
    assert body["total_leads"] == 12
    assert body["rates_known"] is True
    assert body["qualified_leads"] == 5
    assert body["converted_leads"] == 3
    funnel = {row["stage"]: row for row in body["funnel"]}
    assert funnel["capture"]["reached"] == 12 and funnel["capture"]["current"] == 7
    assert funnel["qualify"]["reached"] == 5 and funnel["qualify"]["current"] == 2
    assert funnel["convert"]["reached"] == 3 and funnel["convert"]["current"] == 3
    assert funnel["qualify"]["reached_rate_pct"] == 41.7
    # Campaign breakdown: attributed vs explicit unattributed bucket.
    camps = {row["key"]: row for row in body["campaigns"]}
    assert camps["Eid promo"]["total"] == 6 and camps["Eid promo"]["qualified"] == 5
    assert camps["(unattributed)"]["total"] == 6 and camps["(unattributed)"]["qualified"] == 0
    # UTM breakdown only contains the stated source (missing stays missing).
    assert sorted(row["key"] for row in body["utm_sources"]) == ["(unattributed)", "instagram"]
    assert any("not enforced" in n for n in body["notes"])


def test_rates_unknown_below_threshold(client):
    headers = register(client, email="reports2@leadcrafttest.com")
    capture(client, "Only lead", campaign="Tiny")
    body = client.get("/api/reports/funnel", headers=headers).json()
    assert body["total_leads"] == 1
    assert body["rates_known"] is False
    assert body["qualified_rate_pct"] is None and body["converted_rate_pct"] is None
    assert all(row["reached_rate_pct"] is None for row in body["funnel"])
    assert body["campaigns"][0]["qualified_rate_pct"] is None
    assert any("too early" in n for n in body["notes"])


def test_empty_window_and_tenant_isolation(client):
    headers = register(client, email="reports3@leadcrafttest.com")
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "reportsother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    capture(client, "Private lead")
    body = client.get("/api/reports/funnel", headers=oh).json()
    assert body["total_leads"] == 0
    assert any("No leads in this window" in n for n in body["notes"])
    assert client.get("/api/reports/funnel").status_code == 401
