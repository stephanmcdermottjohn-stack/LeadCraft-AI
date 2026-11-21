"""P5 #1: booking & appointments - slot math, consent-first booking, roles,
tenant isolation. Zero network, zero external providers.
"""
import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TZ = ZoneInfo("Asia/Karachi")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'booking.db'}")
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


def register(client, email="book@leadcrafttest.com", slug="book-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def tomorrow() -> str:
    return (datetime.datetime.now(TZ).date() + datetime.timedelta(days=1)).isoformat()


def configure(client, headers, **overrides):
    body = {
        "enabled": True,
        "days": [0, 1, 2, 3, 4, 5, 6],
        "start": "09:00",
        "end": "12:00",
        "slot_minutes": 30,
        "lead_minutes": 0,
        "timezone": "Asia/Karachi",
        "services": ["Haircut", "Bridal makeup"],
        "note": "Please arrive 5 minutes early.",
    }
    body.update(overrides)
    res = client.patch("/api/appointments/availability", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["availability"]


def slots(client, slug, date=None):
    res = client.get(f"/api/public/landing/{slug}/slots", params={"date": date or tomorrow()})
    assert res.status_code == 200, res.text
    return res.json()


def book(client, slug, slot, **overrides):
    body = {
        "name": "Ayesha Khan",
        "phone": "0300 1234567",
        "email": "ayesha@example.com",
        "service": "Haircut",
        "intent_notes": "Short trim please",
        "starts_at": slot["starts_at"],
        "consent": True,
        "company": "",
    }
    body.update(overrides)
    return client.post(f"/api/public/landing/{slug}/book", json=body)


def invite_accept(client, owner, email, role):
    res = client.post("/api/team/invite", json={"email": email, "role": role}, headers=owner)
    token = res.json()["member"]["invite_path"].split("invite=", 1)[1]
    member = register(client, email=email, slug=None)
    assert client.post("/api/team/accept", json={"token": token}, headers=member).status_code == 200
    return member


def test_booking_is_disabled_by_default(client):
    headers = register(client)
    availability = client.get("/api/appointments/availability", headers=headers).json()
    assert availability["availability"]["enabled"] is False
    assert availability["availability"]["days"] == []
    assert availability["can_edit"] is True

    cfg = client.get("/api/public/landing/book-salon").json()
    assert cfg["booking"]["enabled"] is False

    assert slots(client, "book-salon")["slots"] == []
    res = book(client, "book-salon", {"starts_at": "2030-01-01T10:00:00+00:00"})
    assert res.status_code == 400 and "not enabled" in res.json()["detail"]


def test_availability_validation_and_slot_generation(client):
    headers = register(client)
    # Enabling without working days is refused.
    assert (
        client.patch(
            "/api/appointments/availability", json={"enabled": True, "days": []}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.patch("/api/appointments/availability", json={"days": [7]}, headers=headers).status_code == 400
    )
    assert (
        client.patch("/api/appointments/availability", json={"timezone": "Mars/Base"}, headers=headers).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/appointments/availability", json={"start": "18:00", "end": "09:00"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.patch("/api/appointments/availability", json={"slot_minutes": 5}, headers=headers).status_code
        == 400
    )

    settings = configure(client, headers)
    assert settings["enabled"] is True and settings["services"] == ["Haircut", "Bridal makeup"]
    assert settings["note"] == "Please arrive 5 minutes early."

    body = slots(client, "book-salon")
    assert body["enabled"] is True
    assert body["slot_minutes"] == 30 and body["services"] == ["Haircut", "Bridal makeup"]
    labels = [s["label"] for s in body["slots"]]
    assert labels == ["9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM"]
    assert all(s["starts_at"].endswith("+00:00") for s in body["slots"])


def test_public_booking_creates_consented_lead_and_reuses_it(client):
    headers = register(client)
    configure(client, headers)
    body = slots(client, "book-salon")
    first_slot, second_slot = body["slots"][0], body["slots"][1]

    res = book(client, "book-salon", first_slot)
    assert res.status_code == 201, res.text
    payload = res.json()
    assert payload["appointment"]["status"] == "booked"
    assert payload["appointment"]["label"].startswith(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))
    assert "does not send confirmation" in payload["message"]
    assert payload["lead_created"] is True

    leads = client.get("/api/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    lead = leads[0]
    assert lead["source"] == "landing_page"
    assert lead["consent_timestamp"] is not None
    assert lead["metadata"]["entry_point"] == "booking"
    assert lead["metadata"]["service"] == "Haircut"

    appointments = client.get("/api/appointments", headers=headers).json()
    assert appointments["count"] == 1
    assert appointments["appointments"][0]["lead_phone"] == "0300 1234567"
    assert appointments["timezone"] == "Asia/Karachi"
    assert "no SMS" in appointments["note"]

    # Same slot cannot be double-booked.
    assert book(client, "book-salon", first_slot).status_code == 409
    # The booked slot disappears from the public list.
    remaining = [s["starts_at"] for s in slots(client, "book-salon")["slots"]]
    assert first_slot["starts_at"] not in remaining

    # A repeat customer with the same phone reuses the lead (no duplicates).
    assert book(client, "book-salon", second_slot).status_code == 201
    assert len(client.get("/api/leads", headers=headers).json()["leads"]) == 1
    assert client.get("/api/appointments", headers=headers).json()["count"] == 2

    # Consent is mandatory and arbitrary times are refused.
    assert book(client, "book-salon", body["slots"][2], consent=False).status_code == 400
    fake = {"starts_at": (datetime.datetime.fromisoformat(body["slots"][2]["starts_at"]) + datetime.timedelta(minutes=7)).isoformat()}
    assert book(client, "book-salon", fake).status_code == 409
    # Honeypot.
    assert book(client, "book-salon", body["slots"][2], company="bot").status_code == 400


def test_slots_respect_working_days_window_and_lead_time(client):
    headers = register(client)
    tomorrow_date = datetime.datetime.now(TZ).date() + datetime.timedelta(days=1)
    configure(client, headers, days=[tomorrow_date.weekday()])
    assert len(slots(client, "book-salon")["slots"]) == 6
    # A different weekday is closed.
    other = tomorrow_date + datetime.timedelta(days=1)
    assert slots(client, "book-salon", other.isoformat())["slots"] == []
    # Past and far-future dates are outside the window.
    yesterday = (datetime.datetime.now(TZ).date() - datetime.timedelta(days=1)).isoformat()
    far = (datetime.datetime.now(TZ).date() + datetime.timedelta(days=90)).isoformat()
    assert slots(client, "book-salon", yesterday)["slots"] == []
    assert slots(client, "book-salon", far)["slots"] == []
    # Minimum notice: one week of notice removes tomorrow's slots.
    configure(client, headers, lead_minutes=10080)
    assert slots(client, "book-salon")["slots"] == []


def test_owner_management_manual_entry_and_roles(client):
    owner = register(client)
    configure(client, owner)
    first = slots(client, "book-salon")["slots"][0]
    booked = book(client, "book-salon", first).json()["appointment"]
    appointment_id = client.get("/api/appointments", headers=owner).json()["appointments"][0]["id"]

    patched = client.patch(
        f"/api/appointments/{appointment_id}",
        json={"status": "confirmed", "reminded": True, "owner_notes": "Called to confirm"},
        headers=owner,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["appointment"]["status"] == "confirmed"
    assert patched.json()["appointment"]["reminded_at"] is not None
    assert "manual" in patched.json()["note"]
    assert (
        client.patch(f"/api/appointments/{appointment_id}", json={"status": "maybe"}, headers=owner).status_code
        == 400
    )

    # Manual entry (phone booking) with owner-attested consent.
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)).replace(
        second=0, microsecond=0
    )
    manual = client.post(
        "/api/appointments",
        json={
            "starts_at": future.isoformat(),
            "name": "Walk In",
            "phone": "0321 9999999",
            "consent": True,
            "service": "Haircut",
        },
        headers=owner,
    )
    assert manual.status_code == 201, manual.text
    assert manual.json()["appointment"]["source"] == "manual"
    assert manual.json()["lead_created"] is True
    assert "no confirmation" in manual.json()["note"]
    assert (
        client.post(
            "/api/appointments",
            json={"starts_at": future.isoformat(), "name": "No Consent", "phone": "0321 1111111", "consent": False},
            headers=owner,
        ).status_code
        == 400
    )
    past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat()
    assert (
        client.post(
            "/api/appointments",
            json={"starts_at": past, "name": "Past", "phone": "0321 2222222", "consent": True},
            headers=owner,
        ).status_code
        == 400
    )

    # Agent: operational writes yes, schedule configuration no.
    agent = invite_accept(client, owner, "bookagent@leadcrafttest.com", "agent")
    assert client.get("/api/appointments", headers=agent).status_code == 200
    assert client.patch(f"/api/appointments/{appointment_id}", json={"status": "completed"}, headers=agent).status_code == 200
    assert (
        client.patch("/api/appointments/availability", json={"enabled": False}, headers=agent).status_code == 403
    )

    # Viewer: read-only by the global gate.
    viewer = invite_accept(client, owner, "bookviewer@leadcrafttest.com", "viewer")
    assert client.get("/api/appointments", headers=viewer).status_code == 200
    assert client.patch(f"/api/appointments/{appointment_id}", json={"status": "no_show"}, headers=viewer).status_code == 403
    assert client.post("/api/appointments", json={"starts_at": future.isoformat(), "name": "X", "consent": True}, headers=viewer).status_code == 403

    # Another workspace sees and mutates nothing.
    other = register(client, email="other@leadcrafttest.com", slug="other-salon")
    assert client.get("/api/appointments", headers=other).json()["count"] == 0
    assert client.patch(f"/api/appointments/{appointment_id}", json={"status": "cancelled"}, headers=other).status_code == 404

    # Unauthenticated access is refused.
    assert client.get("/api/appointments").status_code == 401


def test_public_booking_unknown_slug_and_bad_date(client):
    assert client.get("/api/public/landing/nope/slots").status_code == 404
    assert client.post("/api/public/landing/nope/book", json={"name": "X", "consent": True, "starts_at": "2030-01-01T10:00:00Z"}).status_code == 404
    headers = register(client)
    configure(client, headers)
    assert client.get("/api/public/landing/book-salon/slots", params={"date": "not-a-date"}).status_code == 400
