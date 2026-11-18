"""P1 #1: landing page A/B variants + honest report. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ab.db'}")
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
        json={"business_name": "Gulberg Salon", "email": "ab@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "ab-salon", "niche": "bridal makeup"}, headers=headers)
    return headers


def _variant(label="B", **over):
    return {"label": label, "headline": f"{label} headline", "subtext": "limited offer",
            "cta_label": "Book now", "is_active": True, **over}


def test_variant_crud_and_tenant_isolation(client, env):
    headers = env
    res = client.post("/api/landing-variants", json=_variant(), headers=headers)
    assert res.status_code == 201, res.text
    vid = res.json()["variant"]["id"]

    # "control" label and junk labels rejected.
    assert client.post("/api/landing-variants", json=_variant("control"), headers=headers).status_code == 422
    assert client.post("/api/landing-variants", json=_variant("bad label!"), headers=headers).status_code == 422
    # Duplicate label (case-insensitive) -> 409.
    assert client.post("/api/landing-variants", json=_variant("b"), headers=headers).status_code == 409
    # Rename refused (would orphan past traffic).
    assert client.patch(f"/api/landing-variants/{vid}", json=_variant("C"), headers=headers).status_code == 400
    # Content update OK.
    res = client.patch(f"/api/landing-variants/{vid}", json=_variant("B", headline="New head"), headers=headers)
    assert res.json()["variant"]["headline"] == "New head"

    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "abother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/landing-variants", headers=oh).json()["variants"] == []
    assert client.patch(f"/api/landing-variants/{vid}", json=_variant("B"), headers=oh).status_code == 404
    assert client.delete(f"/api/landing-variants/{vid}", headers=oh).status_code == 404

    # Cap: 5 variants max.
    for i in range(4):
        assert client.post("/api/landing-variants", json=_variant(f"V{i}"), headers=headers).status_code == 201
    assert client.post("/api/landing-variants", json=_variant("W"), headers=headers).status_code == 400


def test_public_assignment_and_explicit_rerun(client, env):
    headers = env
    client.post("/api/landing-variants", json=_variant(), headers=headers)
    # No explicit variant: server assigns one of the active arms.
    labels = set()
    for _ in range(12):
        body = client.get("/api/public/landing/ab-salon").json()
        labels.add(body["ab_variant"])
        assert body["variant"]["headline"] in ("B headline",) or body["ab_variant"] == "control"
    assert labels <= {"control", "B"} and labels  # always a valid arm
    # Explicit re-run of the same arm.
    body = client.get("/api/public/landing/ab-salon", params={"variant": "B"}).json()
    assert body["ab_variant"] == "B" and body["variant"]["cta_label"] == "Book now"
    body = client.get("/api/public/landing/ab-salon", params={"variant": "control"}).json()
    assert body["ab_variant"] == "control" and body["variant"] is None
    # Unknown arm -> 404, unknown slug -> 404.
    assert client.get("/api/public/landing/ab-salon", params={"variant": "Z"}).status_code == 404
    assert client.get("/api/public/landing/nope-page").status_code == 404


def test_impression_endpoint(client, env):
    headers = env
    client.post("/api/landing-variants", json=_variant(), headers=headers)
    assert client.post("/api/public/landing/ab-salon/impression", json={"variant": "B"}).status_code == 204
    assert client.post("/api/public/landing/ab-salon/impression", json={"variant": "control"}).status_code == 204
    # Bogus variant label falls back to control counting, not an error.
    assert client.post("/api/public/landing/ab-salon/impression", json={"variant": "ZZZ"}).status_code == 204
    assert client.post("/api/public/landing/nope/impression").status_code == 204  # silent, no leak
    report = client.get("/api/landing-variants/report", headers=headers).json()
    by_arm = {a["arm"]: a for a in report["arms"]}
    assert by_arm["B"]["impressions"] == 1
    assert by_arm["control"]["impressions"] == 2  # bogus label counts as control


def test_report_honest_rates_and_qualified(client, env):
    headers = env
    client.post("/api/landing-variants", json=_variant(), headers=headers)
    # 40 control impressions + 2 B impressions.
    for _ in range(40):
        client.post("/api/public/landing/ab-salon/impression", json={"variant": "control"})
    for _ in range(2):
        client.post("/api/public/landing/ab-salon/impression", json={"variant": "B"})
    # 10 control submissions, one of them qualified (stage moved).
    for i in range(10):
        client.post(
            "/api/leads/capture",
            json={"slug": "ab-salon", "name": f"L{i}", "phone": "0300", "consent": True,
                  "landing_variant": "control"},
        )
    # owner moves one lead to qualify
    leads = client.get("/api/leads", headers=headers).json()["leads"]
    client.patch(f"/api/leads/{leads[0]['id']}/stage", json={"stage": "qualify"}, headers=headers)
    # 1 B submission
    client.post(
        "/api/leads/capture",
        json={"slug": "ab-salon", "name": "BLead", "phone": "0311", "consent": True, "landing_variant": "B"},
    )

    report = client.get("/api/landing-variants/report", headers=headers).json()
    by_arm = {a["arm"]: a for a in report["arms"]}
    control, b = by_arm["control"], by_arm["B"]
    assert control["impressions"] == 40 and control["submissions"] == 10 and control["qualified"] == 1
    assert control["submission_rate_pct"] == 25.0
    assert b["impressions"] == 2 and b["submissions"] == 1
    assert b["submission_rate_pct"] is None and "too early" in b["note"]


def test_report_empty_slug_and_no_variants(client, env):
    headers = env
    report = client.get("/api/landing-variants/report", headers=headers).json()
    assert len(report["arms"]) == 1  # control only
    arm = report["arms"][0]
    assert arm["impressions"] == 0 and arm["submissions"] == 0
    assert arm["submission_rate_pct"] is None and "No traffic" in arm["note"]
