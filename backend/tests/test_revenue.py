"""P5 #3: revenue & ROI tracking - manual, per-currency, honest nulls.

Zero network, zero external providers.
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'revenue.db'}")
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


def register(client, email="revenue@leadcrafttest.com", slug="revenue-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Revenue Salon", "email": email, "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        assert client.patch("/api/settings", json={"landing_slug": slug}, headers=headers).status_code == 200
    return headers


def invite(client, owner, email, role):
    res = client.post("/api/team/invite", json={"email": email, "role": role}, headers=owner)
    assert res.status_code == 201, res.text
    token = res.json()["member"]["invite_path"].split("invite=", 1)[1]
    member = register(client, email=email, slug=None)
    assert client.post("/api/team/accept", json={"token": token}, headers=member).status_code == 200
    return member


def capture(client, slug="revenue-salon", name="Ayesha Khan", phone="0300 1234567", campaign=""):
    res = client.post(
        "/api/leads/capture",
        json={
            "slug": slug,
            "name": name,
            "phone": phone,
            "consent": True,
            "campaign": campaign,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["lead"]["id"]


def put_outcome(client, headers, lead_id, **body):
    payload = {"status": "open", "amount": 0, "currency": "PKR"}
    payload.update(body)
    return client.put(f"/api/leads/{lead_id}/outcome", json=payload, headers=headers)


def test_revenue_routes_require_owner_admin_or_manager(client):
    owner = register(client)
    agent = invite(client, owner, "revagent@leadcrafttest.com", "agent")
    viewer = invite(client, owner, "revviewer@leadcrafttest.com", "viewer")
    manager = invite(client, owner, "revmanager@leadcrafttest.com", "manager")
    lead_id = capture(client)

    # Unauthenticated -> 401 everywhere.
    assert client.get(f"/api/leads/{lead_id}/outcome").status_code == 401
    assert client.put(f"/api/leads/{lead_id}/outcome", json={"status": "won", "amount": 1}).status_code == 401
    assert client.delete(f"/api/leads/{lead_id}/outcome").status_code == 401
    assert client.get("/api/reports/revenue").status_code == 401

    # Agent and viewer -> 403 (money is owner/admin/manager territory).
    for headers in (agent, viewer):
        assert client.get(f"/api/leads/{lead_id}/outcome", headers=headers).status_code == 403
        assert put_outcome(client, headers, lead_id, status="won", amount=1000).status_code == 403
        assert client.delete(f"/api/leads/{lead_id}/outcome", headers=headers).status_code == 403
        assert client.get("/api/reports/revenue", headers=headers).status_code == 403

    # Owner and manager can read + write.
    assert client.get(f"/api/leads/{lead_id}/outcome", headers=owner).status_code == 200
    assert client.get("/api/reports/revenue", headers=manager).status_code == 200
    assert put_outcome(client, manager, lead_id, status="won", amount=1000).status_code == 200


def test_outcome_validation_and_upsert(client):
    owner = register(client)
    lead_id = capture(client)

    assert put_outcome(client, owner, lead_id, status="maybe").status_code == 400
    assert put_outcome(client, owner, lead_id, status="won", amount=-1).status_code == 400
    assert put_outcome(client, owner, lead_id, status="won", amount=10, currency="P").status_code == 400
    assert put_outcome(client, owner, lead_id, status="won", amount=10, currency="pkr1").status_code == 400
    assert (
        put_outcome(client, owner, lead_id, status="won", amount=10, closed_at="2026-13-01").status_code
        == 400
    )
    tomorrow = (utc_today() + datetime.timedelta(days=1)).isoformat()
    assert (
        put_outcome(client, owner, lead_id, status="won", amount=10, closed_at=tomorrow).status_code
        == 400
    )

    # Open deals never carry a closed date, even if one is sent.
    opened = put_outcome(client, owner, lead_id, status="open", amount=25000, closed_at=tomorrow)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["created"] is True
    assert body["outcome"]["status"] == "open"
    assert body["outcome"]["closed_at"] is None
    assert body["outcome"]["amount"] == 25000
    assert body["outcome"]["currency"] == "PKR"

    # Upsert: same lead, one row. Won with an explicit close date.
    today = utc_today().isoformat()
    won = put_outcome(
        client, owner, lead_id, status="won", amount=75000.5, currency="pkr", closed_at=today, note="bridal"
    )
    assert won.status_code == 200, won.text
    assert won.json()["created"] is False
    outcome = won.json()["outcome"]
    assert outcome["status"] == "won"
    assert outcome["currency"] == "PKR"  # normalised
    assert outcome["amount"] == 75000.5
    assert outcome["closed_at"] == today
    assert outcome["note"] == "bridal"

    view = client.get(f"/api/leads/{lead_id}/outcome", headers=owner).json()
    assert view["outcome"]["id"] == outcome["id"]
    assert view["can_edit"] is True

    # Timeline: every write is an append-only activity, never a silent update.
    timeline = client.get(f"/api/leads/{lead_id}/timeline", headers=owner).json()["timeline"]
    deal_events = [e for e in timeline if e["type"] == "deal_outcome"]
    assert len(deal_events) == 2  # open save + won upsert
    assert any("won: PKR 75000.5" in e["text"] for e in deal_events)


def test_outcome_clear_makes_revenue_unknown_again(client):
    owner = register(client)
    lead_id = capture(client)
    assert put_outcome(client, owner, lead_id, status="won", amount=12000).status_code == 200

    removed = client.delete(f"/api/leads/{lead_id}/outcome", headers=owner)
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed"] is True
    assert client.get(f"/api/leads/{lead_id}/outcome", headers=owner).json()["outcome"] is None
    assert client.delete(f"/api/leads/{lead_id}/outcome", headers=owner).status_code == 404

    timeline = client.get(f"/api/leads/{lead_id}/timeline", headers=owner).json()["timeline"]
    assert any(e["type"] == "deal_outcome_cleared" for e in timeline)

    report = client.get("/api/reports/revenue", headers=owner).json()
    assert report["totals_by_currency"] == []
    assert report["coverage"]["leads_total"] == 1
    assert report["coverage"]["leads_with_outcome"] == 0


def test_report_totals_per_currency_and_honest_null_roi(client):
    owner = register(client)
    today = utc_today().isoformat()
    won_pkr = capture(client, name="Won PKR", phone="0300 1110001", campaign="meta-q4")
    won_usd = capture(client, name="Won USD", phone="0300 1110002")
    lost_pkr = capture(client, name="Lost PKR", phone="0300 1110003")
    open_pkr = capture(client, name="Open PKR", phone="0300 1110004")

    assert put_outcome(client, owner, won_pkr, status="won", amount=100000, closed_at=today).status_code == 200
    assert (
        put_outcome(client, owner, won_usd, status="won", amount=500, currency="USD", closed_at=today).status_code
        == 200
    )
    assert put_outcome(client, owner, lost_pkr, status="lost", amount=20000, closed_at=today).status_code == 200
    assert put_outcome(client, owner, open_pkr, status="open", amount=30000).status_code == 200

    report = client.get("/api/reports/revenue?days=30", headers=owner).json()
    assert report["window_days"] == 30
    assert report["outcomes"] == {
        "won_deals": 2,
        "lost_deals": 1,
        "closed_deals": 3,
        "open_deals": 1,
        "win_rate_pct": None,  # gate: < 10 closed deals
        "rates_known": False,
        "rate_gate": 10,
    }
    assert report["coverage"] == {
        "leads_total": 4,
        "leads_with_outcome": 4,
        "coverage_pct": 100.0,
    }

    by_currency = {row["currency"]: row for row in report["totals_by_currency"]}
    assert set(by_currency) == {"PKR", "USD"}
    pkr = by_currency["PKR"]
    assert pkr["revenue"] == 100000.0
    assert pkr["won_deals"] == 1
    assert pkr["avg_deal"] == 100000.0
    assert pkr["lost_deals"] == 1
    assert pkr["lost_value"] == 20000.0
    assert pkr["open_deals"] == 1
    assert pkr["open_value"] == 30000.0
    assert pkr["spend"] == 0.0
    assert pkr["roi_pct"] is None  # no spend in PKR -> unknown, not 0%
    assert pkr["cost_per_won"] is None

    usd = by_currency["USD"]
    assert usd["revenue"] == 500.0
    assert usd["spend"] == 0.0
    assert usd["roi_pct"] is None
    assert any("never converts" in note for note in report["notes"])

    # Spend only in PKR: ROI appears for PKR only, USD stays unknown.
    spend = client.put(
        "/api/campaign-spend",
        json={"campaign": "meta-q4", "spend": 50000, "currency": "PKR"},
        headers=owner,
    )
    assert spend.status_code in (200, 201), spend.text
    # Spend with no recorded won deal must NOT become a -100% ROI: revenue is
    # unknown, so the ROI stays null for that currency.
    assert (
        client.put(
            "/api/campaign-spend",
            json={"campaign": "offline", "spend": 1000, "currency": "AED"},
            headers=owner,
        ).status_code
        in (200, 201)
    )

    report = client.get("/api/reports/revenue?days=30", headers=owner).json()
    by_currency = {row["currency"]: row for row in report["totals_by_currency"]}
    assert by_currency["PKR"]["spend"] == 50000.0
    assert by_currency["PKR"]["roi_pct"] == 100.0  # (100000-50000)/50000
    assert by_currency["PKR"]["cost_per_won"] == 50000.0
    assert by_currency["USD"]["roi_pct"] is None
    assert by_currency["AED"]["spend"] == 1000.0
    assert by_currency["AED"]["won_deals"] == 0
    assert by_currency["AED"]["roi_pct"] is None
    assert by_currency["AED"]["cost_per_won"] is None

    campaigns = {(c["campaign"], c["currency"]): c for c in report["campaigns"]}
    assert campaigns[("meta-q4", "PKR")]["won_deals"] == 1
    assert campaigns[("meta-q4", "PKR")]["revenue"] == 100000.0
    assert campaigns[("meta-q4", "PKR")]["spend"] == 50000.0
    assert campaigns[("meta-q4", "PKR")]["roi_pct"] == 100.0
    assert campaigns[("meta-q4", "PKR")]["cost_per_won"] == 50000.0
    assert (("meta-q4", "USD") in campaigns) is False  # spend and revenue currencies never mix
    assert (("(unattributed)", "PKR") in campaigns) is False
    assert campaigns[("(unattributed)", "USD")]["revenue"] == 500.0
    assert campaigns[("(unattributed)", "USD")]["spend"] == 0.0
    assert campaigns[("(unattributed)", "USD")]["roi_pct"] is None
    assert campaigns[("offline", "AED")]["won_deals"] == 0
    assert campaigns[("offline", "AED")]["roi_pct"] is None
    assert campaigns[("offline", "AED")]["cost_per_won"] is None
    assert any("(unattributed)" in note for note in report["notes"])


def test_win_rate_needs_ten_closed_deals(client):
    owner = register(client)
    today = utc_today().isoformat()
    ids = [capture(client, name=f"Lead {i}", phone=f"0300 200{i:04d}") for i in range(10)]
    for i, lead_id in enumerate(ids):
        status = "won" if i < 6 else "lost"
        assert (
            put_outcome(client, owner, lead_id, status=status, amount=1000, closed_at=today).status_code == 200
        )

    report = client.get("/api/reports/revenue?days=30", headers=owner).json()
    assert report["outcomes"]["closed_deals"] == 10
    assert report["outcomes"]["won_deals"] == 6
    assert report["outcomes"]["lost_deals"] == 4
    assert report["outcomes"]["win_rate_pct"] == 60.0
    assert report["outcomes"]["rates_known"] is True

    # A 1-day window that excludes the deals keeps the rate unknown, not 0%.
    old = (utc_today() - datetime.timedelta(days=60)).isoformat()
    for lead_id in ids[:10]:
        assert (
            put_outcome(
                client, owner, lead_id, status="won" if lead_id in ids[:6] else "lost", amount=1000, closed_at=old
            ).status_code
            == 200
        )
    narrowed = client.get("/api/reports/revenue?days=7", headers=owner).json()
    assert narrowed["outcomes"]["closed_deals"] == 0
    assert narrowed["outcomes"]["won_deals"] == 0
    assert narrowed["outcomes"]["win_rate_pct"] is None
    assert narrowed["outcomes"]["rates_known"] is False


def test_revenue_is_tenant_scoped(client):
    owner = register(client)
    lead_id = capture(client)
    assert put_outcome(client, owner, lead_id, status="won", amount=90000).status_code == 200

    other = register(client, email="revother@leadcrafttest.com", slug="revenue-other")

    # Another workspace cannot read, write or delete this lead's outcome.
    assert client.get(f"/api/leads/{lead_id}/outcome", headers=other).status_code == 404
    assert put_outcome(client, other, lead_id, status="won", amount=1).status_code == 404
    assert client.delete(f"/api/leads/{lead_id}/outcome", headers=other).status_code == 404

    other_report = client.get("/api/reports/revenue", headers=other).json()
    assert other_report["totals_by_currency"] == []
    assert other_report["coverage"]["leads_total"] == 0
    assert other_report["outcomes"]["won_deals"] == 0

    owner_report = client.get("/api/reports/revenue", headers=owner).json()
    assert owner_report["outcomes"]["won_deals"] == 1
    assert owner_report["totals_by_currency"][0]["revenue"] == 90000.0
