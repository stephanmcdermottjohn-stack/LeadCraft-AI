"""P1 #2: nurture workflows - consent-gated, suppressed contacts, due steps.
Zero network, no message sending."""
import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'nurture.db'}")
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
        json={"business_name": "Gulberg Salon", "email": "nur@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "nur-salon"}, headers=headers)
    cap = client.post(
        "/api/leads/capture", json={"slug": "nur-salon", "name": "Ayesha", "phone": "03001112222", "consent": True}
    )
    lid = cap.json()["lead"]["id"]
    camp = client.post(
        "/api/nurture/campaigns",
        json={"name": "3-touch follow-up", "steps": [
            {"day_offset": 0, "message": "Day 0: intro call"},
            {"day_offset": 2, "message": "Day 2: send offer"},
        ]},
        headers=headers,
    )
    return headers, lid, camp.json()["campaign"]["id"]


def test_campaign_validation_and_crud(client, env):
    headers, lid, cid = env
    # Too few/many steps, bad offsets, empty messages -> 400 (steps validated in the service).
    assert client.post("/api/nurture/campaigns", json={"name": "x", "steps": []}, headers=headers).status_code == 400
    assert client.post("/api/nurture/campaigns",
                       json={"name": "x", "steps": [{"day_offset": -1, "message": "hi"}]}, headers=headers).status_code == 400
    assert client.post("/api/nurture/campaigns",
                       json={"name": "x", "steps": [{"day_offset": 0, "message": "  "}]}, headers=headers).status_code == 400
    many = [{"day_offset": i, "message": f"step {i}"} for i in range(9)]
    assert client.post("/api/nurture/campaigns", json={"name": "x", "steps": many}, headers=headers).status_code == 400
    # Update works.
    res = client.patch(f"/api/nurture/campaigns/{cid}",
                       json={"name": "renamed", "steps": [{"day_offset": 0, "message": "intro"}], "active": False},
                       headers=headers)
    assert res.json()["campaign"]["name"] == "renamed" and res.json()["campaign"]["active"] is False
    # Tenant isolation.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "nurother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/nurture/campaigns", headers=oh).json()["campaigns"] == []
    assert client.patch(f"/api/nurture/campaigns/{cid}",
                        json={"name": "x", "steps": [{"day_offset": 0, "message": "m"}]}, headers=oh).status_code == 404


def test_enroll_duplicate_consent_and_inactive(client, env):
    headers, lid, cid = env
    res = client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers)
    assert res.status_code == 201, res.text
    assert res.json()["outcome"] == "active"
    assert res.json()["enrollment"]["status"] == "active"
    # Duplicate enrollment in the same campaign -> 409.
    assert client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers).status_code == 409
    # Lead without consent (direct insert not possible; consent is mandatory at
    # capture) - use another user's lead -> 404.
    other_lead = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "nuro2@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other_lead.json()['token']}"}
    assert client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=oh).status_code == 404
    # Inactive campaign refuses new enrollments.
    client.patch(f"/api/nurture/campaigns/{cid}",
                 json={"name": "3-touch follow-up", "steps": [{"day_offset": 0, "message": "m"}], "active": False},
                 headers=headers)
    assert client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers).status_code == 400


def test_due_steps_surface_as_next_action(client, env):
    headers, lid, cid = env
    res = client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers)
    eid = res.json()["enrollment"]["id"]
    # Step 0 (day 0) is due immediately.
    run = client.post("/api/nurture/process-due", headers=headers).json()
    assert run["steps_surfaced"] >= 1
    lead = next(l for l in client.get("/api/leads", headers=headers).json()["leads"] if l["id"] == lid)
    assert lead["next_action"] == "Day 0: intro call"
    assert lead["next_action_at"] is not None
    # Step 1 is 2 days out - not surfaced yet.
    run2 = client.post("/api/nurture/process-due", headers=headers).json()
    assert run2["steps_surfaced"] == 0
    enrollment = client.get("/api/nurture/enrollments", headers=headers).json()["enrollments"][0]
    assert enrollment["status"] == "active" and enrollment["current_step"] == 1
    # Timeline activity logged.
    tl = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    assert any("Nurture" in e["text"] for e in tl)
    # Stop before completion.
    client.post(f"/api/nurture/enrollments/{eid}/stop", headers=headers)
    enrollment = client.get("/api/nurture/enrollments", headers=headers).json()["enrollments"][0]
    assert enrollment["status"] == "stopped"


def test_sequence_completes_after_last_step(client, env, monkeypatch):
    headers, lid, cid = env
    client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers)
    # Simulate 3 days passing: backdate the enrollment via process worker path.
    from sqlalchemy import select

    from app import db as db_module
    from app.models import NurtureEnrollment

    db = db_module.SessionLocal()
    enr = db.scalars(select(NurtureEnrollment)).all()[0]
    enr.enrolled_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
    db.commit()
    db.close()
    run = client.post("/api/nurture/process-due", headers=headers).json()
    assert run["steps_surfaced"] == 2  # both steps catch up in order
    enrollment = client.get("/api/nurture/enrollments", headers=headers).json()["enrollments"][0]
    assert enrollment["status"] == "completed" and enrollment["current_step"] == 2
    lead = next(l for l in client.get("/api/leads", headers=headers).json()["leads"] if l["id"] == lid)
    assert lead["next_action"] == "Day 2: send offer"  # last surfaced step wins
    # Metrics reflect completion.
    camp = client.get("/api/nurture/campaigns", headers=headers).json()["campaigns"][0]
    m = camp["metrics"]
    assert m["completed"] == 1 and m["enrolled_total"] == 1


def test_suppression_blocks_active_enrollment(client, env):
    headers, lid, cid = env
    # Suppress the lead's phone before enrolling.
    client.post("/api/nurture/suppressions", json={"value": "0300 1112222", "reason": "asked to stop"}, headers=headers)
    res = client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers)
    assert res.status_code == 201
    assert res.json()["outcome"] == "suppressed"
    assert res.json()["enrollment"]["status"] == "suppressed"
    # Duplicate suppression -> 409.
    assert client.post("/api/nurture/suppressions", json={"value": "03001112222"}, headers=headers).status_code == 409
    # Suppression list shows normalized value.
    sup = client.get("/api/nurture/suppressions", headers=headers).json()["suppressions"]
    assert sup[0]["value"] == "03001112222" and sup[0]["reason"] == "asked to stop"
    # Remove suppression + delete (fresh enrollment becomes active).
    client.delete(f"/api/nurture/suppressions/{sup[0]['id']}", headers=headers)
    # Campaign delete blocked while an enrollment exists (suppressed counts).
    assert client.delete(f"/api/nurture/campaigns/{cid}", headers=headers).status_code == 400


def test_worker_pass_function(client, env):
    headers, lid, cid = env
    client.post(f"/api/nurture/campaigns/{cid}/enroll", json={"lead_id": lid}, headers=headers)
    from app import db as db_module
    from app.workers.nurture_worker import run_due_pass

    db = db_module.SessionLocal()
    surfaced = run_due_pass(db)
    db.close()
    assert surfaced >= 1
