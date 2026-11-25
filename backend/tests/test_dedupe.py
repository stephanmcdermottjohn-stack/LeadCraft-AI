"""P6 #1: duplicate lead detection & safe merge.

No network, no external providers. Covers normalization, tenant isolation, role
gates, dry-run previews, history reassignment, honest deal/qualification rules,
conversation + nurture de-duplication, and referral relinking.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'dedupe.db'}")
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


def register(client, email="dedupe@leadcrafttest.com", slug="dedupe-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Dedupe Salon", "email": email, "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        assert client.patch("/api/settings", json={"landing_slug": slug}, headers=headers).status_code == 200
    return headers


def invite(client, owner, email, role, slug=None):
    res = client.post("/api/team/invite", json={"email": email, "role": role}, headers=owner)
    assert res.status_code == 201, res.text
    token = res.json()["member"]["invite_path"].split("invite=", 1)[1]
    member = register(client, email=email, slug=slug)
    assert client.post("/api/team/accept", json={"token": token}, headers=member).status_code == 200
    return member


def capture(client, slug="dedupe-salon", name="Lead", phone="", email="", **extra):
    payload = {"slug": slug, "name": name, "phone": phone, "email": email, "consent": True}
    payload.update(extra)
    res = client.post("/api/leads/capture", json=payload)
    assert res.status_code == 201, res.text
    return res.json()["lead"]["id"]


def merge(client, headers, primary_id, duplicate_ids, dry_run=False):
    return client.post(
        "/api/leads/merge",
        json={"primary_id": primary_id, "duplicate_ids": duplicate_ids, "dry_run": dry_run},
        headers=headers,
    )


def test_detection_normalizes_phone_and_email(client):
    owner = register(client)
    a = capture(client, name="Ayesha", phone="0300 1234567", email="Same@Example.com")
    b = capture(client, name="Ayesha B", phone="+92 (300) 123-4567", email="b@example.com")
    c = capture(client, name="Ayesha C", phone="0321 7654321", email="same@example.com")
    d = capture(client, name="Different", phone="0321 1111111", email="d@example.com")

    groups = client.get("/api/leads/duplicates", headers=owner).json()
    assert groups["groups_total"] == 1, groups
    group = groups["groups"][0]
    assert {row["id"] for row in group["leads"]} == {a, b, c}
    assert set(group["matched_on"]) == {"phone", "email"}

    per_lead = client.get(f"/api/leads/{a}/duplicates", headers=owner).json()
    by_id = {row["id"]: row for row in per_lead["candidates"]}
    assert set(by_id) == {b, c}
    assert by_id[b]["matched_on"] == ["phone"]
    assert "email differs" in by_id[b]["conflicts"]
    assert by_id[c]["matched_on"] == ["email"]
    assert "phone differs" in by_id[c]["conflicts"]

    assert client.get(f"/api/leads/{d}/duplicates", headers=owner).json()["candidates"] == []


def test_detection_and_merge_are_tenant_scoped(client):
    owner1 = register(client, email="one@leadcrafttest.com", slug="tenant-one")
    owner2 = register(client, email="two@leadcrafttest.com", slug="tenant-two")
    a = capture(client, slug="tenant-one", name="One", phone="0300 5550001")
    b = capture(client, slug="tenant-two", name="Two", phone="0300 5550001")

    assert client.get("/api/leads/duplicates", headers=owner1).json()["groups_total"] == 0
    assert client.get("/api/leads/duplicates", headers=owner2).json()["groups_total"] == 0

    blocked = merge(client, owner1, a, [b])
    assert blocked.status_code == 404, blocked.text
    assert client.get(f"/api/leads/{b}/duplicates", headers=owner2).json()["candidates"] == []


def test_merge_is_owner_admin_only(client):
    owner = register(client)
    admin = invite(client, owner, "dedupeadmin@leadcrafttest.com", "admin")
    manager = invite(client, owner, "dedupemanager@leadcrafttest.com", "manager")
    agent = invite(client, owner, "dedupeagent@leadcrafttest.com", "agent")
    viewer = invite(client, owner, "dedupeviewer@leadcrafttest.com", "viewer")

    a = capture(client, name="Primary", phone="0345 1112223")
    b = capture(client, name="Duplicate", phone="+92 345 1112223")

    assert merge(client, {}, a, [b], dry_run=True).status_code == 401
    for headers in (agent, viewer, manager):
        res = merge(client, headers, a, [b], dry_run=True)
        assert res.status_code == 403, res.text

    # Admin can preview; owner does the actual merge.
    assert merge(client, admin, a, [b], dry_run=True).status_code == 200
    res = merge(client, owner, a, [b])
    assert res.status_code == 200, res.text
    assert res.json()["merged"] is True


def test_dry_run_changes_nothing(client):
    owner = register(client)
    a = capture(client, name="Primary", phone="0300 7770001")
    b = capture(client, name="Duplicate", phone="+92 300 7770001")
    assert client.post(f"/api/leads/{b}/notes", json={"body": "from duplicate"}, headers=owner).status_code == 201

    preview = merge(client, owner, a, [b], dry_run=True)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["merged"] is False and body["dry_run"] is True
    assert body["moved"]["notes"] == 1
    assert len(body["primary"]) > 0

    assert len(client.get("/api/leads", headers=owner).json()["leads"]) == 2
    assert client.get(f"/api/leads/{b}/notes", headers=owner).status_code == 200

    actual = merge(client, owner, a, [b])
    assert actual.status_code == 200, actual.text
    assert actual.json()["moved"]["notes"] == 1
    assert len(client.get("/api/leads", headers=owner).json()["leads"]) == 1
    assert client.get(f"/api/leads/{b}/notes", headers=owner).status_code == 404
    notes = client.get(f"/api/leads/{a}/notes", headers=owner).json()["notes"]
    assert notes[0]["body"] == "from duplicate"


def test_merge_moves_history_and_fills_only_unknowns(client):
    owner = register(client)
    a = capture(client, name="Primary", phone="0300 8880001")
    b = capture(client, name="Duplicate", phone="+92 300 8880001", intent_notes="wants bridal package")

    assert client.patch(
        f"/api/leads/{a}/qualification", json={"budget": "100000"}, headers=owner
    ).status_code == 200
    assert client.patch(
        f"/api/leads/{b}/qualification",
        json={"budget": "999999", "need": "bridal"},
        headers=owner,
    ).status_code == 200
    assert client.put(
        f"/api/leads/{b}/outcome",
        json={"status": "won", "amount": 50000, "currency": "PKR"},
        headers=owner,
    ).status_code == 200
    assert client.post(f"/api/leads/{b}/notes", json={"body": "met at expo"}, headers=owner).status_code == 201
    assert client.patch(f"/api/leads/{b}/status", json={"status": "contacted"}, headers=owner).status_code == 200

    res = merge(client, owner, a, [b])
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["merged"] is True
    assert summary["moved"]["notes"] == 1
    assert any("qualification.budget kept primary" in c for c in summary["conflicts"])

    qualification = client.get(f"/api/leads/{a}/qualification", headers=owner).json()["qualification"]
    assert qualification["dimensions"]["budget"]["value"] == "100000"  # known primary wins
    assert qualification["dimensions"]["need"]["value"] == "bridal"    # unknown filled

    outcome = client.get(f"/api/leads/{a}/outcome", headers=owner).json()["outcome"]
    assert outcome["status"] == "won" and outcome["amount"] == 50000.0

    timeline = client.get(f"/api/leads/{a}/timeline", headers=owner).json()["timeline"]
    kinds = {event["type"] for event in timeline}
    assert "note" in kinds
    assert "status_changed" in kinds
    assert "duplicate_merged" in kinds
    assert any("met at expo" in event["text"] for event in timeline)
    assert "wants bridal package" in client.get("/api/leads", headers=owner).json()["leads"][0]["intent_notes"]

    audit = client.get("/api/ops/audit?action=lead.merged", headers=owner).json()
    assert audit["count"] == 1
    assert audit["entries"][0]["target_id"] == str(a)


def test_deal_outcomes_are_never_summed(client):
    owner = register(client)
    a = capture(client, name="Primary", phone="0300 9990001")
    b = capture(client, name="Duplicate", phone="+92 300 9990001")
    assert client.put(
        f"/api/leads/{a}/outcome",
        json={"status": "won", "amount": 10000, "currency": "PKR"},
        headers=owner,
    ).status_code == 200
    assert client.put(
        f"/api/leads/{b}/outcome",
        json={"status": "won", "amount": 50000, "currency": "PKR"},
        headers=owner,
    ).status_code == 200

    res = merge(client, owner, a, [b])
    assert res.status_code == 200, res.text
    assert any("not summed" in c for c in res.json()["conflicts"])

    outcome = client.get(f"/api/leads/{a}/outcome", headers=owner).json()["outcome"]
    assert outcome["amount"] == 10000.0
    report = client.get("/api/reports/revenue?days=365", headers=owner).json()
    pkr = next(row for row in report["totals_by_currency"] if row["currency"] == "PKR")
    assert pkr["won_deals"] == 1
    assert pkr["revenue"] == 10000.0


def test_same_channel_conversations_and_nurture_do_not_duplicate(client):
    owner = register(client)
    a = capture(client, name="Primary", phone="0300 2220001")
    b = capture(client, name="Duplicate", phone="+92 300 2220001")

    conv_a = client.post(
        "/api/inbox/conversations", json={"lead_id": a, "channel": "whatsapp_inbound"}, headers=owner
    ).json()["conversation"]["id"]
    conv_b = client.post(
        "/api/inbox/conversations", json={"lead_id": b, "channel": "whatsapp_inbound"}, headers=owner
    ).json()["conversation"]["id"]
    assert client.post(
        f"/api/inbox/conversations/{conv_a}/messages",
        json={"direction": "in", "body": "hello from primary"},
        headers=owner,
    ).status_code == 201
    assert client.post(
        f"/api/inbox/conversations/{conv_b}/messages",
        json={"direction": "in", "body": "hello from duplicate"},
        headers=owner,
    ).status_code == 201

    campaign = client.post(
        "/api/nurture/campaigns",
        json={"name": "Dedupe campaign", "steps": [{"day_offset": 1, "message": "follow up"}]},
        headers=owner,
    ).json()["campaign"]["id"]
    for lead_id in (a, b):
        assert client.post(
            f"/api/nurture/campaigns/{campaign}/enroll", json={"lead_id": lead_id}, headers=owner
        ).status_code == 201

    res = merge(client, owner, a, [b])
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["moved"]["conversations_merged"] == 1
    assert summary["moved"]["messages"] == 1
    assert any("nurture enrollment" in c for c in summary["conflicts"])

    conversations = client.get("/api/inbox/conversations", headers=owner).json()["conversations"]
    same_lead = [c for c in conversations if c["lead_id"] == a and c["channel"] == "whatsapp_inbound"]
    assert len(same_lead) == 1
    messages = client.get(
        f"/api/inbox/conversations/{same_lead[0]['id']}/messages", headers=owner
    ).json()["messages"]
    assert {m["body"] for m in messages} == {"hello from primary", "hello from duplicate"}

    enrollments = client.get(
        f"/api/nurture/enrollments?campaign_id={campaign}", headers=owner
    ).json()["enrollments"]
    assert len(enrollments) == 1
    assert enrollments[0]["lead_id"] == a


def test_referrals_are_relinked_to_the_primary(client):
    owner = register(client)
    a = capture(client, name="Primary", phone="0300 3330001")
    b = capture(client, name="Duplicate", phone="+92 300 3330001")
    code = client.post(f"/api/referrals/leads/{b}/code", headers=owner).json()["code"]
    c = capture(client, name="Referred", phone="0300 3330002", referral_code=code)

    from app import db as db_module

    with db_module.SessionLocal() as session:
        from app.models import Lead

        assert session.get(Lead, c).referred_by_lead_id == b

    res = merge(client, owner, a, [b])
    assert res.status_code == 200, res.text
    assert res.json()["moved"]["referred_leads"] == 1

    with db_module.SessionLocal() as session:
        from app.models import Lead

        referred = session.get(Lead, c)
        assert referred.referred_by_lead_id == a
        assert session.get(Lead, a).referral_code == code
