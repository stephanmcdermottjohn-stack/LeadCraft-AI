"""P2 #2: advanced attribution - coverage, capture-time-only honesty, spend
registry, cost ratios, time-to-stage medians. Zero network."""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'attribution.db'}")
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


def register(client, email="attr@leadcrafttest.com", slug="attr-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def capture(client, name, campaign="", utm_source="", slug="attr-salon"):
    return client.post(
        "/api/leads/capture",
        json={
            "slug": slug, "name": name, "phone": "03001112222", "consent": True,
            "campaign": campaign, "utm_source": utm_source,
        },
    ).json()["lead"]["id"]


def backdate(lead_id, days):
    from app import db as db_module
    from app.models import Lead

    db = db_module.SessionLocal()
    lead = db.get(Lead, lead_id)
    lead.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    db.commit()
    db.close()


def test_spend_registry_crud_and_tenant(client):
    headers = register(client)
    res = client.put("/api/campaign-spend", json={"campaign": "Eid promo", "spend": 5000}, headers=headers)
    assert res.status_code == 200, res.text
    first_id = res.json()["spend"]["id"]
    # Upsert same campaign -> same row, new amount.
    res = client.put("/api/campaign-spend", json={"campaign": "Eid promo", "spend": 6000, "notes": "boosted"}, headers=headers)
    assert res.json()["spend"]["id"] == first_id and res.json()["spend"]["spend"] == 6000.0
    assert len(client.get("/api/campaign-spend", headers=headers).json()["spends"]) == 1
    # Validation.
    assert client.put("/api/campaign-spend", json={"campaign": "x", "spend": -1}, headers=headers).status_code == 422
    assert client.put("/api/campaign-spend", json={"campaign": "  ", "spend": 10}, headers=headers).status_code == 400
    # Tenant isolation.
    other = register(client, email="attrother@leadcrafttest.com", slug="attr-other")
    assert client.get("/api/campaign-spend", headers=other).json()["spends"] == []
    assert client.delete(f"/api/campaign-spend/{first_id}", headers=other).status_code == 404
    assert client.delete(f"/api/campaign-spend/{first_id}", headers=headers).status_code == 204


def test_report_coverage_costs_and_honesty(client):
    headers = register(client)
    for i in range(6):
        capture(client, f"A{i}", campaign="Eid promo", utm_source="instagram")
    for i in range(3):
        capture(client, f"B{i}", utm_source="google")
    for i in range(3):
        capture(client, f"C{i}")
    leads = client.get("/api/leads", headers=headers).json()["leads"]
    a_ids = [l["id"] for l in leads if l["name"].startswith("A")]
    for lid in a_ids[:3]:
        client.patch(f"/api/leads/{lid}/stage", json={"stage": "qualify"}, headers=headers)
    client.patch(f"/api/leads/{a_ids[0]}/stage", json={"stage": "convert"}, headers=headers)
    client.put("/api/campaign-spend", json={"campaign": "Eid promo", "spend": 6000}, headers=headers)

    body = client.get("/api/attribution/report?days=30", headers=headers).json()
    cov = body["coverage"]
    assert cov["leads"] == 12
    assert cov["campaign_tagged"] == 6 and cov["utm_tagged"] == 9 and cov["any_tagged"] == 9
    assert cov["campaign_coverage_pct"] == 50.0 and cov["any_coverage_pct"] == 75.0
    assert body["rates_known"] is True
    camps = {c["campaign"]: c for c in body["campaigns"]}
    eid = camps["Eid promo"]
    assert eid["leads"] == 6 and eid["qualified"] == 3 and eid["converted"] == 1
    assert eid["spend"] == 6000.0 and eid["currency"] == "PKR"
    assert eid["cost_per_lead"] == 1000.0
    assert eid["cost_per_qualified"] == 2000.0
    assert eid["cost_per_conversion"] == 6000.0
    # No spend -> costs unknown, never invented.
    assert camps["(unattributed)"]["spend"] is None
    assert camps["(unattributed)"]["cost_per_lead"] is None
    assert sorted(u["utm_source"] for u in body["utm_sources"]) == ["(unattributed)", "google", "instagram"]
    notes = " ".join(body["notes"])
    assert "multi-touch" in notes and "ROI is not computed" in notes
    assert body["median_time_to_qualify_days"] is not None


def test_time_to_stage_median_uses_platform_timestamps(client):
    headers = register(client, email="attrtime@leadcrafttest.com", slug="attr-time")
    ids = [capture(client, f"T{i}", slug="attr-time") for i in range(3)]
    for lid, days in zip(ids, (2, 4, 9)):
        backdate(lid, days)
        client.patch(f"/api/leads/{lid}/stage", json={"stage": "qualify"}, headers=headers)
    body = client.get("/api/attribution/report", headers=headers).json()
    assert body["time_to_qualify_samples"] == 3
    assert body["median_time_to_qualify_days"] == 4.0
    assert body["median_time_to_convert_days"] is None
    assert any("time-to-convert is unknown" in n for n in body["notes"])


def test_empty_window_and_auth(client):
    headers = register(client, email="attrempty@leadcrafttest.com", slug="attr-empty")
    other = register(client, email="attrempty2@leadcrafttest.com", slug="attr-empty-2")
    capture(client, "Private", slug="attr-empty")
    body = client.get("/api/attribution/report", headers=other).json()
    assert body["coverage"]["leads"] == 0
    assert body["coverage"]["any_coverage_pct"] is None
    assert any("No leads in this window" in n for n in body["notes"])
    assert client.get("/api/attribution/report").status_code == 401
    assert client.get("/api/campaign-spend").status_code == 401
