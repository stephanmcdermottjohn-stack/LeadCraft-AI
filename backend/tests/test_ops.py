"""P5 #2: data, audit & ops - export, audit log, retention, usage.

Zero network, zero external providers.
"""
import datetime
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ops.db'}")
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


def register(client, email="ops@leadcrafttest.com", slug="ops-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Ops Salon", "email": email, "password": "supersecret1"},
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


def capture(client, slug="ops-salon", name="Ayesha Khan", phone="0300 1234567"):
    res = client.post(
        "/api/leads/capture",
        json={"slug": slug, "name": name, "phone": phone, "consent": True},
    )
    assert res.status_code == 201, res.text
    return res.json()


def session():
    from app import db

    return db.SessionLocal()


def test_ops_routes_require_owner_or_admin(client):
    owner = register(client)
    agent = invite(client, owner, "opsagent@leadcrafttest.com", "agent")
    viewer = invite(client, owner, "opsviewer@leadcrafttest.com", "viewer")

    for path in ("/api/ops/usage", "/api/ops/export", "/api/ops/audit", "/api/ops/retention/preview"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=agent).status_code == 403
        assert client.get(path, headers=viewer).status_code == 403

    assert client.post("/api/ops/retention/purge", json={"days": 90, "confirm": True}).status_code == 401
    assert (
        client.post("/api/ops/retention/purge", json={"days": 90, "confirm": True}, headers=agent).status_code
        == 403
    )
    assert client.get("/api/ops/usage", headers=owner).status_code == 200


def test_export_is_complete_scoped_and_audited(client):
    owner = register(client)
    capture(client)
    capture(client, name="Second Lead", phone="0321 9998887")
    # A team member row exists, but its single-use invite token must not leak.
    client.post(
        "/api/team/invite", json={"email": "exported@leadcrafttest.com", "role": "agent"}, headers=owner
    )
    assert client.patch("/api/settings", json={"niche": "bridal makeup"}, headers=owner).status_code == 200
    assert (
        client.post(
            "/api/billing",
            json={"amount": 5000, "currency": "PKR", "note": "cash"},
            headers=owner,
        ).status_code
        == 201
    )
    assert client.patch("/api/billing/plan", json={"plan_tier": "pro"}, headers=owner).status_code == 200

    res = client.get("/api/ops/export", headers=owner)
    assert res.status_code == 200, res.text
    assert "attachment" in res.headers["content-disposition"]
    body = res.json()
    assert body["format"] == "leadcraft-workspace-export"
    assert body["workspace"]["email"] == "ops@leadcrafttest.com"
    assert body["settings"]["niche"] == "bridal makeup"
    assert len(body["data"]["leads"]) == 2
    assert body["data"]["billing_entries"][0]["amount"] == 5000
    assert body["counts"]["leads"] == 2
    assert body["truncated_tables"] == []
    assert any("landing_events" in item for item in body["excluded"])
    # Secrets never leave the server (the excluded list may name them, data must not contain them).
    data_json = json.dumps(body["data"])
    assert "password_hash" not in data_json
    assert "invite_token" not in data_json
    assert all("invite_token" not in m for m in body["data"]["team_members"])

    logs = client.get("/api/ops/audit", headers=owner).json()
    actions = {row["action"] for row in logs["entries"]}
    assert {"settings.updated", "team.invited", "billing.entry_added", "billing.plan_changed", "ops.export"} <= actions
    assert all(row["actor_email"] == "ops@leadcrafttest.com" for row in logs["entries"])
    assert logs["append_only"] is True
    # No secrets in audit details.
    assert "password" not in json.dumps(logs).lower()

    # Tenant isolation: another workspace exports only its own (empty) data.
    other = register(client, email="opsother@leadcrafttest.com", slug="ops-other")
    other_body = client.get("/api/ops/export", headers=other).json()
    assert other_body["data"]["leads"] == []
    assert other_body["workspace"]["email"] == "opsother@leadcrafttest.com"
    other_logs = client.get("/api/ops/audit", headers=other).json()
    assert {row["action"] for row in other_logs["entries"]} == {"settings.updated", "ops.export"}


def test_retention_preview_and_purge_only_telemetry(client):
    owner = register(client)
    capture(client)
    from app.models import AnalyticsEvent, LandingEvent, WebhookEvent

    now = datetime.datetime.now(datetime.timezone.utc)
    old = now - datetime.timedelta(days=120)
    with session() as s:
        s.add_all(
            [
                LandingEvent(user_id=1, slug="ops-salon", variant="control", event="impression", created_at=old),
                LandingEvent(user_id=1, slug="ops-salon", variant="control", event="impression", created_at=now),
                AnalyticsEvent(
                    user_id=1, slug="ops-salon", session_id="sid-1", event="page_view", created_at=old
                ),
                AnalyticsEvent(
                    user_id=1, slug="ops-salon", session_id="sid-2", event="page_view", created_at=now
                ),
                WebhookEvent(
                    source="whatsapp",
                    event_key="old-processed",
                    status="processed",
                    user_id=1,
                    received_at=old,
                ),
                WebhookEvent(
                    source="whatsapp",
                    event_key="old-error",
                    status="error",
                    user_id=1,
                    received_at=old,
                ),
                WebhookEvent(
                    source="whatsapp",
                    event_key="new-processed",
                    status="processed",
                    user_id=1,
                    received_at=now,
                ),
            ]
        )
        s.commit()

    preview = client.get("/api/ops/retention/preview?days=30", headers=owner).json()
    assert preview["days"] == 30
    assert preview["counts"] == {"landing_events": 1, "analytics_events": 1, "webhook_events": 1}
    assert preview["total"] == 3
    assert any("audit log" in kept for kept in preview["kept"])

    assert (
        client.post("/api/ops/retention/purge", json={"days": 30, "confirm": False}, headers=owner).status_code
        == 400
    )
    assert client.get("/api/ops/retention/preview?days=10", headers=owner).status_code == 422

    purged = client.post(
        "/api/ops/retention/purge", json={"days": 30, "confirm": True}, headers=owner
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["deleted"] == {
        "landing_events": 1,
        "analytics_events": 1,
        "webhook_events": 1,
    }

    with session() as s:
        assert s.query(LandingEvent).count() == 1
        assert s.query(AnalyticsEvent).count() == 1
        assert s.query(WebhookEvent).count() == 2  # error row is retryable, not purged
        assert s.query(WebhookEvent).filter_by(event_key="old-error").count() == 1
        from app.models import Lead

        assert s.query(Lead).count() == 1  # business records untouched

    logs = client.get("/api/ops/audit", headers=owner).json()
    purge_rows = [r for r in logs["entries"] if r["action"] == "ops.retention_purged"]
    assert len(purge_rows) == 1
    assert purge_rows[0]["detail"]["deleted"]["webhook_events"] == 1


def test_usage_counts_are_scoped_and_honest(client):
    owner = register(client)
    capture(client)
    starts = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).replace(
        second=0, microsecond=0
    )
    manual = client.post(
        "/api/appointments",
        json={
            "starts_at": starts.isoformat(),
            "name": "Walk In",
            "phone": "0300 1234567",
            "consent": True,
        },
        headers=owner,
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["lead_created"] is False  # same phone reuses the captured lead

    body = client.get("/api/ops/usage", headers=owner).json()
    assert body["counts"]["leads"] == 1
    assert body["counts"]["appointments"] == 1
    assert body["counts"]["team_members_active"] == 0
    assert body["last"]["lead_at"] is not None
    assert body["retention"]["export_row_limit"] > 0
    assert any("not storage bytes" in note for note in body["notes"])

    other = register(client, email="opsusageother@leadcrafttest.com", slug="ops-usage-other")
    other_body = client.get("/api/ops/usage", headers=other).json()
    assert other_body["counts"]["leads"] == 0
    assert other_body["counts"]["appointments"] == 0
    assert other_body["last"]["lead_at"] is None
