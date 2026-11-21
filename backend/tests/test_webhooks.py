"""P4 integrations: Meta Lead Ads + WhatsApp inbound webhooks.

Everything here is offline: HMAC signatures are computed locally and the Graph
API call is monkeypatched, so no network or credentials are needed.
"""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

SECRET = "test-app-secret"
VERIFY = "test-verify-token"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'webhooks.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("META_APP_SECRET", SECRET)
    monkeypatch.setenv("META_VERIFY_TOKEN", VERIFY)
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
    from app import config, db

    config.get_settings.cache_clear()
    db.engine = db.create_engine_for_current_settings()
    db.SessionLocal = db.sessionmaker(bind=db.engine, autoflush=False, expire_on_commit=False, future=True)
    app = create_app()
    with TestClient(app) as c:
        yield c


def sign(raw: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def deliver(client, path: str, payload: dict, secret: str = SECRET):
    raw = json.dumps(payload).encode("utf-8")
    return client.post(
        path,
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(raw, secret)},
    )


def register(client, email="meta@leadcrafttest.com", slug="meta-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def configure(client, headers, page_id="111222333444", phone_id="999888777666"):
    body = {}
    if page_id is not None:
        body["meta_page_id"] = page_id
    if phone_id is not None:
        body["whatsapp_phone_number_id"] = phone_id
    res = client.patch("/api/settings", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["settings"]["integrations"]


def leadgen_payload(leadgen_id="9001", page_id="111222333444"):
    return {
        "object": "page",
        "entry": [
            {
                "id": page_id,
                "time": 1763680000,
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": leadgen_id,
                            "page_id": page_id,
                            "form_id": "form-1",
                            "ad_id": "ad-1",
                            "created_time": 1763680000,
                        },
                    }
                ],
            }
        ],
    }


def whatsapp_payload(
    message_id="wamid.1", phone_id="999888777666", sender="923001234567", text="Hi, need a haircut"
):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "923009998887", "phone_number_id": phone_id},
                            "contacts": [{"profile": {"name": "Ayesha"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": message_id,
                                    "timestamp": "1763680100",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_verify_handshake_is_off_until_configured(client, monkeypatch):
    ok = client.get(
        "/api/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "abc123"},
    )
    assert ok.status_code == 200 and ok.text == "abc123"

    bad = client.get(
        "/api/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "abc123"},
    )
    assert bad.status_code == 403

    # WhatsApp uses the same handshake contract.
    ok_wa = client.get(
        "/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "xyz"},
    )
    assert ok_wa.status_code == 200 and ok_wa.text == "xyz"

    # No verify token -> webhook is honestly reported as not configured.
    monkeypatch.setenv("META_VERIFY_TOKEN", "")
    from app import config

    config.get_settings.cache_clear()
    assert (
        client.get(
            "/api/webhooks/meta",
            params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "abc"},
        ).status_code
        == 503
    )


def test_deliveries_require_a_valid_signature(client):
    headers = register(client)
    configure(client, headers)
    payload = leadgen_payload()

    raw = json.dumps(payload).encode()
    missing = client.post("/api/webhooks/meta", content=raw, headers={"Content-Type": "application/json"})
    assert missing.status_code == 403
    assert deliver(client, "/api/webhooks/meta", payload, secret="wrong-secret").status_code == 403
    # Nothing was stored for rejected deliveries.
    assert client.get("/api/integrations/events", headers=headers).json()["count"] == 0

    # Same rules on the WhatsApp endpoint.
    assert deliver(client, "/api/webhooks/whatsapp", whatsapp_payload(), secret="nope").status_code == 403


def test_leadgen_pending_then_retry_creates_one_lead(client, monkeypatch):
    headers = register(client)
    integrations = configure(client, headers)
    assert integrations["meta_ready"] is False  # no Page access token yet
    payload = leadgen_payload()

    first = deliver(client, "/api/webhooks/meta", payload)
    assert first.status_code == 200
    assert first.json()["received"] == 1
    assert first.json()["pending_credentials"] == 1
    assert first.json()["processed"] == 0

    events = client.get("/api/integrations/events", headers=headers).json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["source"] == "meta_leadgen" and event["status"] == "pending_credentials"
    assert event["signature_valid"] is True and event["lead_id"] is None
    assert "META_PAGE_ACCESS_TOKEN" in event["error"]

    # Provider retry of the same delivery is a no-op (idempotent event key).
    duplicate = deliver(client, "/api/webhooks/meta", payload)
    assert duplicate.json()["duplicates"] == 1 and duplicate.json()["received"] == 0
    assert client.get("/api/integrations/events", headers=headers).json()["count"] == 1

    # Add the token and retry: one lead is created from the stored delivery.
    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    from app import config
    from app.services import meta_leadgen

    config.get_settings.cache_clear()
    captured = {}

    def fake_fetch(leadgen_id, token, version):
        captured.update({"leadgen_id": leadgen_id, "token": token, "version": version})
        return [
            {"name": "full_name", "values": ["Ayesha Khan"]},
            {"name": "phone_number", "values": ["+92 300 1234567"]},
            {"name": "email", "values": ["ayesha@example.com"]},
            {"name": "city", "values": ["Lahore"]},
            {"name": "what_do_you_need", "values": ["Bridal makeup"]},
        ]

    monkeypatch.setattr(meta_leadgen, "fetch_lead_fields", fake_fetch)

    retried = client.post(f"/api/integrations/events/{event['id']}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["event"]["status"] == "processed"
    assert retried.json()["event"]["lead_id"] is not None
    assert captured["leadgen_id"] == "9001" and captured["token"] == "page-token"

    leads = client.get("/api/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["source"] == "meta_lead_ad"
    assert lead["name"] == "Ayesha Khan" and lead["phone"] == "+92 300 1234567"
    assert lead["email"] == "ayesha@example.com" and lead["area"] == "Lahore"
    assert lead["consent_timestamp"] is not None
    assert lead["metadata"]["integration"] == "meta_lead_ad"
    assert lead["metadata"]["answers"]["what_do_you_need"] == "Bridal makeup"

    # A processed event cannot be retried again (no silent duplicate leads).
    again = client.post(f"/api/integrations/events/{event['id']}/retry", headers=headers)
    assert again.status_code == 400
    assert len(client.get("/api/leads", headers=headers).json()["leads"]) == 1


def test_leadgen_unrouted_is_not_assigned_to_a_tenant(client):
    headers = register(client)
    configure(client, headers, page_id=None)
    payload = leadgen_payload(page_id="555000111222")

    res = deliver(client, "/api/webhooks/meta", payload)
    assert res.status_code == 200 and res.json()["unrouted"] == 1
    # Unrouted deliveries belong to no workspace and stay invisible.
    assert client.get("/api/integrations/events", headers=headers).json()["count"] == 0
    assert client.get("/api/leads", headers=headers).json()["leads"] == []


def test_whatsapp_inbound_creates_lead_conversation_and_is_idempotent(client):
    headers = register(client)
    configure(client, headers)
    payload = whatsapp_payload()

    first = deliver(client, "/api/webhooks/whatsapp", payload)
    assert first.status_code == 200, first.text
    assert first.json()["processed"] == 1 and first.json()["received"] == 1
    assert "never auto-replies" in first.json()["note"]

    leads = client.get("/api/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["source"] == "whatsapp_inbound"
    assert lead["name"] == "Ayesha" and lead["phone"] == "923001234567"
    # Consent timestamp is the inbound message time (2025-11-20T22:28:20Z),
    # not the time the webhook happened to be processed.
    assert lead["consent_timestamp"].startswith("2025-11-20")
    assert lead["metadata"]["integration"] == "whatsapp_cloud"

    conversations = client.get("/api/inbox/conversations", headers=headers).json()["conversations"]
    assert len(conversations) == 1
    convo = conversations[0]
    assert convo["channel"] == "whatsapp_inbound" and convo["has_inbound"] is True

    messages = client.get(f"/api/inbox/conversations/{convo['id']}/messages", headers=headers).json()
    assert [m["direction"] for m in messages["messages"]] == ["in"]
    assert messages["messages"][0]["body"] == "Hi, need a haircut"

    # A provider retry must not duplicate the message.
    dup = deliver(client, "/api/webhooks/whatsapp", payload)
    assert dup.json()["duplicates"] == 1 and dup.json()["received"] == 0
    messages = client.get(f"/api/inbox/conversations/{convo['id']}/messages", headers=headers).json()
    assert len(messages["messages"]) == 1

    # A second real message reuses the same lead + conversation.
    second = deliver(client, "/api/webhooks/whatsapp", whatsapp_payload(message_id="wamid.2", text="Tomorrow at 5?"))
    assert second.json()["processed"] == 1
    assert len(client.get("/api/leads", headers=headers).json()["leads"]) == 1
    messages = client.get(f"/api/inbox/conversations/{convo['id']}/messages", headers=headers).json()
    assert [m["body"] for m in messages["messages"]] == ["Hi, need a haircut", "Tomorrow at 5?"]


def test_whatsapp_media_is_labelled_not_downloaded(client):
    headers = register(client)
    configure(client, headers)
    payload = whatsapp_payload()
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"][0] = {
        "from": "923001234567",
        "id": "wamid.media",
        "timestamp": "1763680100",
        "type": "image",
        "image": {"id": "media-1", "mime_type": "image/jpeg"},
    }

    assert deliver(client, "/api/webhooks/whatsapp", payload).json()["processed"] == 1
    convo = client.get("/api/inbox/conversations", headers=headers).json()["conversations"][0]
    messages = client.get(f"/api/inbox/conversations/{convo['id']}/messages", headers=headers).json()
    assert "media not downloaded" in messages["messages"][0]["body"]


def test_events_are_tenant_scoped_and_ops_only(client):
    owner = register(client, email="owner-a@leadcrafttest.com", slug="owner-a")
    other = register(client, email="owner-b@leadcrafttest.com", slug="owner-b")
    configure(client, owner)
    event_id = None

    deliver(client, "/api/webhooks/meta", leadgen_payload())
    events = client.get("/api/integrations/events", headers=owner).json()["events"]
    assert len(events) == 1
    event_id = events[0]["id"]

    # Another workspace sees nothing and cannot read or retry the event.
    assert client.get("/api/integrations/events", headers=other).json()["count"] == 0
    assert client.get(f"/api/integrations/events/{event_id}", headers=other).status_code == 404
    assert client.post(f"/api/integrations/events/{event_id}/retry", headers=other).status_code == 404

    # The workspace event log carries the stored payload for the owner.
    detail = client.get(f"/api/integrations/events/{event_id}", headers=owner).json()["event"]
    assert "9001" in detail["payload"]

    # Unauthenticated access is refused.
    assert client.get("/api/integrations/events").status_code == 401

    # Agent/viewer roles cannot read the event log (payloads contain PII).
    invite = client.post(
        "/api/team/invite", json={"email": "meta-agent@leadcrafttest.com", "role": "agent"}, headers=owner
    ).json()
    token = invite["member"]["invite_path"].split("invite=", 1)[1]
    agent = register(client, email="meta-agent@leadcrafttest.com", slug=None)
    assert client.post("/api/team/accept", json={"token": token}, headers=agent).status_code == 200
    assert client.get("/api/integrations/events", headers=agent).status_code == 403


def test_settings_validate_ids_and_show_readiness(client, monkeypatch):
    headers = register(client)
    settings = client.get("/api/settings", headers=headers).json()["settings"]
    integrations = settings["integrations"]
    assert integrations["meta_webhook_url"] == "/api/webhooks/meta"
    assert integrations["meta_page_id"] == "" and integrations["whatsapp_phone_number_id"] == ""
    assert integrations["meta_app_secret_configured"] is True
    assert integrations["meta_page_access_token_configured"] is False
    assert integrations["meta_ready"] is False and integrations["whatsapp_ready"] is False

    # Numeric ids only.
    assert client.patch("/api/settings", json={"meta_page_id": "page-abc"}, headers=headers).status_code == 400
    assert (
        client.patch("/api/settings", json={"whatsapp_phone_number_id": "12"}, headers=headers).status_code == 400
    )
    ready = configure(client, headers)["whatsapp_ready"]
    assert ready is True  # phone id + verify token + app secret

    monkeypatch.setenv("META_PAGE_ACCESS_TOKEN", "page-token")
    from app import config

    config.get_settings.cache_clear()
    integrations = client.get("/api/settings", headers=headers).json()["settings"]["integrations"]
    assert integrations["meta_ready"] is True

    # Empty string clears a routing id; no secrets are ever returned.
    cleared = client.patch("/api/settings", json={"meta_page_id": "", "whatsapp_phone_number_id": ""}, headers=headers)
    assert cleared.json()["settings"]["integrations"]["meta_page_id"] == ""
    assert "page-token" not in cleared.text and SECRET not in cleared.text


def test_unconfigured_app_secret_returns_503(client, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "")
    from app import config

    config.get_settings.cache_clear()
    res = deliver(client, "/api/webhooks/meta", leadgen_payload(), secret="")
    assert res.status_code == 503
    assert "META_APP_SECRET" in res.json()["detail"]
