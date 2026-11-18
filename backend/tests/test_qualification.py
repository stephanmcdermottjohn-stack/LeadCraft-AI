"""P0 #3: BANT qualification - unknown-first, manual corrections. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'bant.db'}")
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
def lead_id(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "bant@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "bant-salon"}, headers=headers)
    cap = client.post(
        "/api/leads/capture",
        json={"slug": "bant-salon", "name": "Ayesha Khan", "phone": "03001234567", "consent": True},
    )
    return headers, cap.json()["lead"]["id"]


def _dims(q):
    # q is already the unwrapped qualification object (res.json()["qualification"]).
    return q["dimensions"]


def test_unknown_first(client, lead_id):
    headers, lid = lead_id
    res = client.get(f"/api/leads/{lid}/qualification", headers=headers)
    assert res.status_code == 200, res.text
    q = res.json()["qualification"]
    assert q["complete"] == 0 and q["total"] == 4
    assert all(_dims(q)[d]["confidence"] == "unknown" for d in ("budget", "authority", "need", "timing"))
    # No row was created just by reading (lazy create on PATCH only).
    assert q["updated_at"] is None


def test_partial_update_keeps_unknowns(client, lead_id):
    headers, lid = lead_id
    res = client.patch(f"/api/leads/{lid}/qualification", json={"budget": "PKR 150000", "timing": "December wedding"},
                       headers=headers)
    q = res.json()["qualification"]
    dims = _dims(q)
    assert dims["budget"] == {"value": "PKR 150000", "confidence": "known", "source": "manual"}
    assert dims["timing"]["confidence"] == "known"
    assert dims["authority"]["confidence"] == "unknown"
    assert q["complete"] == 2
    assert "Still unknown: authority, need" in q["suggestion"]


def test_complete_bant_suggests_nurture(client, lead_id):
    headers, lid = lead_id
    res = client.patch(
        f"/api/leads/{lid}/qualification",
        json={"budget": "150000", "authority": "bride herself", "need": "bridal makeup package", "timing": "December"},
        headers=headers,
    )
    q = res.json()["qualification"]
    assert q["complete"] == 4
    assert "nurture" in q["suggestion"]


def test_reset_to_unknown(client, lead_id):
    headers, lid = lead_id
    client.patch(f"/api/leads/{lid}/qualification", json={"budget": "150000"}, headers=headers)
    res = client.patch(f"/api/leads/{lid}/qualification", json={"budget": "  "}, headers=headers)
    dims = _dims(res.json()["qualification"])
    assert dims["budget"] == {"value": "", "confidence": "unknown", "source": ""}
    assert res.json()["qualification"]["complete"] == 0


def test_tenant_isolation_and_validation(client, lead_id):
    headers, lid = lead_id
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "bantother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get(f"/api/leads/{lid}/qualification", headers=oh).status_code == 404
    assert client.patch(f"/api/leads/{lid}/qualification", json={"budget": "1"}, headers=oh).status_code == 404
    # Empty body -> 400 (nothing to update).
    assert client.patch(f"/api/leads/{lid}/qualification", json={}, headers=headers).status_code == 400
    # >500 chars -> 422.
    assert client.patch(f"/api/leads/{lid}/qualification", json={"budget": "x" * 501}, headers=headers).status_code == 422
