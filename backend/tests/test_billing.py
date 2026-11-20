"""P3 #3: manual billing ledger - CRUD, currency-grouped totals, plan label,
role gates. No payment processing anywhere; zero network.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'billing.db'}")
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


def register(client, email="pay@leadcrafttest.com", slug="pay-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def invite_accept(client, owner, email, role):
    res = client.post("/api/team/invite", json={"email": email, "role": role}, headers=owner)
    token = res.json()["member"]["invite_path"].split("invite=", 1)[1]
    member = register(client, email=email, slug=None)
    assert client.post("/api/team/accept", json={"token": token}, headers=member).status_code == 200
    return member


def test_ledger_crud_totals_and_validation(client):
    headers = register(client)
    assert client.get("/api/billing", headers=headers).json() == {
        "plan_tier": "basic",
        "entries": [],
        "entry_count": 0,
        "totals_by_currency": {},
        "latest_paid_until": None,
        "plan_tiers": ["basic", "pro", "agency"],
        "notes": [
            "Manual ledger only - no payment gateway, no card data, no auto-charging.",
            "Totals are grouped per currency; no exchange-rate conversion is applied.",
            "Changing the plan tier does not create a charge and does not enforce limits in this version.",
        ],
    }

    first = client.post(
        "/api/billing",
        json={
            "amount": 15000,
            "currency": "pkr",
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
            "paid_until": "2026-12-01",
            "note": "cash received",
        },
        headers=headers,
    )
    assert first.status_code == 201, first.text
    row = first.json()["entry"]
    assert row["currency"] == "PKR" and row["amount"] == 15000.0
    assert row["period_start"] == "2026-11-01" and row["paid_until"] == "2026-12-01"

    client.post("/api/billing", json={"amount": 50, "currency": "USD"}, headers=headers)
    client.post("/api/billing", json={"amount": 5000, "currency": "PKR"}, headers=headers)

    body = client.get("/api/billing", headers=headers).json()
    assert body["entry_count"] == 3
    # Grouped per currency, never summed across currencies.
    assert body["totals_by_currency"] == {"PKR": 20000.0, "USD": 50.0}
    assert body["latest_paid_until"] == "2026-12-01"

    # Validation.
    assert client.post("/api/billing", json={"amount": 0}, headers=headers).status_code == 400
    assert client.post("/api/billing", json={"amount": -5}, headers=headers).status_code == 400
    bad_period = client.post(
        "/api/billing",
        json={"amount": 100, "period_start": "2026-12-01", "period_end": "2026-11-01"},
        headers=headers,
    )
    assert bad_period.status_code == 400 and "period_end" in bad_period.json()["detail"]
    assert client.post("/api/billing", json={"amount": 10, "currency": "P"}, headers=headers).status_code == 400

    # Delete is tenant-checked and permanent.
    deleted = client.delete(f"/api/billing/{row['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.delete(f"/api/billing/{row['id']}", headers=headers).status_code == 404
    assert client.get("/api/billing", headers=headers).json()["entry_count"] == 2


def test_plan_label_is_manual_and_validated(client):
    headers = register(client)
    res = client.patch("/api/billing/plan", json={"plan_tier": "Pro"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["plan_tier"] == "pro" and "no charge" in res.json()["note"]
    me = client.get("/api/auth/me", headers=headers).json()["user"]
    assert me["plan_tier"] == "pro"
    # No ledger row was created by changing the label.
    assert client.get("/api/billing", headers=headers).json()["entry_count"] == 0
    assert client.patch("/api/billing/plan", json={"plan_tier": "unlimited"}, headers=headers).status_code == 400


def test_billing_is_tenant_scoped(client):
    a = register(client, email="paya@leadcrafttest.com", slug="pay-a")
    b = register(client, email="payb@leadcrafttest.com", slug="pay-b")
    row = client.post("/api/billing", json={"amount": 999}, headers=a).json()["entry"]
    assert client.get("/api/billing", headers=b).json()["entries"] == []
    assert client.delete(f"/api/billing/{row['id']}", headers=b).status_code == 404
    assert client.get("/api/billing", headers=a).json()["entry_count"] == 1


def test_billing_roles(client):
    owner = register(client, email="payowner@leadcrafttest.com", slug="pay-owner")
    admin = invite_accept(client, owner, "payadmin@leadcrafttest.com", "admin")
    agent = invite_accept(client, owner, "payagent@leadcrafttest.com", "agent")
    viewer = invite_accept(client, owner, "payviewer@leadcrafttest.com", "viewer")

    # Admin can record a payment; agent and viewer cannot even read the ledger.
    assert client.get("/api/billing", headers=admin).status_code == 200
    assert client.post("/api/billing", json={"amount": 1200}, headers=admin).status_code == 201
    assert client.post("/api/billing", json={"amount": 1200}, headers=agent).status_code == 403
    assert client.get("/api/billing", headers=viewer).status_code == 403
    assert client.patch("/api/billing/plan", json={"plan_tier": "agency"}, headers=agent).status_code == 403
    # Owner shares the workspace ledger.
    assert client.get("/api/billing", headers=owner).json()["entry_count"] == 1
    assert client.get("/api/billing").status_code == 401
