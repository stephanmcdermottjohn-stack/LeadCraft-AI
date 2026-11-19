"""P2 #1: reviews & referrals - consent-first, converted-only reviews,
link-based referrals, honest rate gates. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'reviews.db'}")
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


def register(client, email="reviews@leadcrafttest.com", slug="reviews-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def capture(client, slug="reviews-salon", name="Ayesha", referral_code=""):
    res = client.post(
        "/api/leads/capture",
        json={
            "slug": slug,
            "name": name,
            "phone": "03001112222",
            "consent": True,
            "referral_code": referral_code,
        },
    )
    return res.json()["lead"]["id"]


def test_review_requires_converted_lead_and_no_duplicates(client):
    headers = register(client)
    lid = capture(client)
    # Not converted yet -> refused.
    res = client.post("/api/reviews", json={"lead_id": lid, "channel": "whatsapp"}, headers=headers)
    assert res.status_code == 400 and "converted" in res.json()["detail"]
    client.patch(f"/api/leads/{lid}/stage", json={"stage": "convert"}, headers=headers)
    # Bad channel -> 400.
    assert client.post("/api/reviews", json={"lead_id": lid, "channel": "sms"}, headers=headers).status_code == 400
    res = client.post("/api/reviews", json={"lead_id": lid, "channel": "phone", "note": "asked after bridal trial"}, headers=headers)
    assert res.status_code == 201, res.text
    review = res.json()["review"]
    assert review["status"] == "requested" and review["channel"] == "phone"
    # Duplicate open request -> 400.
    assert client.post("/api/reviews", json={"lead_id": lid, "channel": "phone"}, headers=headers).status_code == 400
    # Resolve -> completed, completion summary honest.
    res = client.patch(f"/api/reviews/{review['id']}", json={"status": "completed", "note": "left a Google review"}, headers=headers)
    assert res.json()["review"]["status"] == "completed" and res.json()["review"]["completed_at"]
    # Already resolved -> 400 (no silent double-logging).
    assert client.patch(f"/api/reviews/{review['id']}", json={"status": "declined"}, headers=headers).status_code == 400
    body = client.get("/api/reviews", headers=headers).json()
    assert body["summary"]["total"] == 1 and body["summary"]["completed"] == 1
    assert body["summary"]["completion_rate_pct"] == 100.0
    # Timeline activity logged (owner's own ask, not a platform send).
    tl = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    assert any(e["type"] == "review" and "requested" in e["text"] for e in tl)


def test_review_summary_empty_is_null_not_zero(client):
    headers = register(client, email="reviews2@leadcrafttest.com", slug="reviews-salon-2")
    body = client.get("/api/reviews", headers=headers).json()
    assert body["summary"]["total"] == 0
    assert body["summary"]["completion_rate_pct"] is None


def test_referral_code_and_capture_link(client):
    headers = register(client)
    referrer = capture(client, name="Nadia")
    res = client.post(f"/api/referrals/leads/{referrer}/code", headers=headers)
    assert res.status_code == 200, res.text
    code = res.json()["code"]
    assert code.startswith("ref") and res.json()["path"] == f"/l/reviews-salon?ref={code}"
    # Stable code on repeat call.
    assert client.post(f"/api/referrals/leads/{referrer}/code", headers=headers).json()["code"] == code

    referred = capture(client, name="Sana", referral_code=code)
    leads = {l["id"]: l for l in client.get("/api/leads", headers=headers).json()["leads"]}
    assert leads[referred]["referred_by_lead_id"] == referrer
    assert leads[referrer]["referred_by_lead_id"] is None
    # Unknown code -> ignored, no error (public form never reveals codes).
    unlinked = capture(client, name="Hina", referral_code="refdoesnotexist")
    leads = {l["id"]: l for l in client.get("/api/leads", headers=headers).json()["leads"]}
    assert leads[unlinked]["referred_by_lead_id"] is None


def test_referral_report_and_tenant_isolation(client):
    headers = register(client)
    referrer = capture(client, name="Nadia")
    code = client.post(f"/api/referrals/leads/{referrer}/code", headers=headers).json()["code"]
    r1 = capture(client, name="Sana", referral_code=code)
    r2 = capture(client, name="Hira", referral_code=code)
    client.patch(f"/api/leads/{r1}/stage", json={"stage": "convert"}, headers=headers)
    client.patch(f"/api/leads/{r2}/stage", json={"stage": "qualify"}, headers=headers)

    body = client.get("/api/referrals/report", headers=headers).json()
    assert body["referrals_total"] == 2
    assert body["qualified_total"] == 2 and body["converted_total"] == 1
    assert body["rates_known"] is False
    assert body["converted_rate_pct"] is None  # too early, never 0%
    top = body["referrers"][0]
    assert top["lead_id"] == referrer and top["referrals"] == 2 and top["code"] == code
    assert top["conversion_rate_pct"] is None
    assert any("Only link-based referrals" in n for n in body["notes"])

    # Cross-tenant: another business's code is ignored on this slug.
    other = register(client, email="reviewsother@leadcrafttest.com", slug="reviews-other")
    other_lead = capture(client, slug="reviews-other", name="Other Lead")
    other_code = client.post(f"/api/referrals/leads/{other_lead}/code", headers=other).json()["code"]
    stranger = capture(client, name="Stranger", referral_code=other_code)
    leads = {l["id"]: l for l in client.get("/api/leads", headers=headers).json()["leads"]}
    assert leads[stranger]["referred_by_lead_id"] is None
    # Other tenant cannot read this report's numbers.
    oh = client.get("/api/referrals/report", headers=other).json()
    assert oh["referrals_total"] == 0
    assert client.get("/api/referrals/report").status_code == 401
