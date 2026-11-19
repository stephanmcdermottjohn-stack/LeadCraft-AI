"""P1 #3: unified inbox v1 - consent-first, tenant-checked. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'inbox.db'}")
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
        json={"business_name": "Gulberg Salon", "email": "inbox@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "inbox-salon"}, headers=headers)
    cap = client.post(
        "/api/leads/capture", json={"slug": "inbox-salon", "name": "Ayesha", "phone": "03001112222", "consent": True}
    )
    return headers, cap.json()["lead"]["id"]


def test_conversation_create_and_channel_validation(client, env):
    headers, lid = env
    res = client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "whatsapp_inbound"}, headers=headers)
    assert res.status_code == 201, res.text
    conv = res.json()["conversation"]
    assert conv["has_inbound"] is False and conv["last_message_preview"] == ""
    # Unknown channel -> 400.
    assert client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "sms"}, headers=headers).status_code == 400


def test_outbound_first_refused_consent_first_ok(client, env):
    headers, lid = env
    conv = client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "whatsapp_inbound"}, headers=headers).json()["conversation"]
    # Outbound-first is the core consent violation -> 400.
    res = client.post(f"/api/inbox/conversations/{conv['id']}/messages",
                      json={"direction": "out", "body": "Hi! Buy from us"}, headers=headers)
    assert res.status_code == 400
    assert "Outbound-first" in res.json()["detail"]
    # Lead spoke first -> outbound reply allowed.
    r1 = client.post(f"/api/inbox/conversations/{conv['id']}/messages",
                     json={"direction": "in", "body": "Do you have bridal slots in December?"}, headers=headers)
    assert r1.status_code == 201
    r2 = client.post(f"/api/inbox/conversations/{conv['id']}/messages",
                     json={"direction": "out", "body": "Yes - December 20-22 is open. Shall I book?"}, headers=headers)
    assert r2.status_code == 201
    thread = client.get(f"/api/inbox/conversations/{conv['id']}/messages", headers=headers).json()
    assert [m["direction"] for m in thread["messages"]] == ["in", "out"]
    assert thread["conversation"]["has_inbound"] is True
    assert thread["conversation"]["last_message_at"] is not None


def test_list_conversations_sorted_with_preview(client, env):
    headers, lid = env
    c1 = client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "website_chat"}, headers=headers).json()["conversation"]
    client.post(f"/api/inbox/conversations/{c1['id']}/messages",
                json={"direction": "in", "body": "First inbound message here"}, headers=headers)
    listing = client.get("/api/inbox/conversations", headers=headers).json()["conversations"]
    assert len(listing) == 1
    assert listing[0]["last_message_preview"].startswith("First inbound")
    assert listing[0]["channel"] == "website_chat"


def test_tenant_isolation(client, env):
    headers, lid = env
    conv = client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "direct_message"}, headers=headers).json()["conversation"]
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "inboxother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/inbox/conversations", headers=oh).json()["conversations"] == []
    assert client.get(f"/api/inbox/conversations/{conv['id']}/messages", headers=oh).status_code == 404
    assert client.post(f"/api/inbox/conversations/{conv['id']}/messages",
                       json={"direction": "in", "body": "hi"}, headers=oh).status_code == 404


def test_message_validation_and_timeline_merge(client, env):
    headers, lid = env
    conv = client.post("/api/inbox/conversations", json={"lead_id": lid, "channel": "whatsapp_inbound"}, headers=headers).json()["conversation"]
    cid = conv["id"]
    # Bad direction, empty body, >2000 chars.
    assert client.post(f"/api/inbox/conversations/{cid}/messages", json={"direction": "xyz", "body": "hi"}, headers=headers).status_code == 400
    assert client.post(f"/api/inbox/conversations/{cid}/messages", json={"direction": "in", "body": "   "}, headers=headers).status_code == 422
    assert client.post(f"/api/inbox/conversations/{cid}/messages", json={"direction": "in", "body": "x" * 2001}, headers=headers).status_code == 422
    client.post(f"/api/inbox/conversations/{cid}/messages", json={"direction": "in", "body": "thread message"}, headers=headers)
    tl = client.get(f"/api/leads/{lid}/timeline", headers=headers).json()["timeline"]
    msgs = [e for e in tl if e["type"] == "message"]
    assert len(msgs) == 1 and "thread message" in msgs[0]["text"] and "whatsapp_inbound" in msgs[0]["text"]
