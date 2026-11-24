"""Security gate: login / registration brute-force throttling.

Covers the documented gap "no login rate limiting / lockout":
- 5 failed logins for one email+IP -> 429 with Retry-After
- a correct password is still refused while locked
- a successful login resets the email+IP counter
- another IP is unaffected (no cross-user lockout)
- unknown emails give the exact same 401 as a wrong password
- registration attempts are capped per IP
- the throttle table stores SHA-256 hashes only (no plaintext email/IP)
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'limits.db'}")
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


IP_A = {"X-Forwarded-For": "203.0.113.10"}
IP_B = {"X-Forwarded-For": "203.0.113.20"}

EMAIL = "limits@leadcrafttest.com"
PASSWORD = "correct-horse-1"


def _register(client, email: str = EMAIL, password: str = PASSWORD, headers=None):
    return client.post(
        "/api/auth/register",
        json={"business_name": "Limits Salon", "email": email, "password": password},
        headers=headers or IP_A,
    )


def _login(client, password: str, *, email: str = EMAIL, headers=None):
    return client.post("/api/auth/login", json={"email": email, "password": password}, headers=headers or IP_A)


def test_five_failures_lock_even_the_correct_password(client):
    assert _register(client).status_code == 201

    for attempt in range(5):
        res = _login(client, "wrong-password")
        assert res.status_code == 401, f"attempt {attempt}: {res.text}"
        assert res.json()["detail"] == "Invalid email or password."

    blocked = _login(client, PASSWORD)
    assert blocked.status_code == 429
    wait = int(blocked.headers["Retry-After"])
    assert 1 <= wait <= 15 * 60

    # Still locked on the next try, with a fresh Retry-After.
    again = _login(client, PASSWORD)
    assert again.status_code == 429
    assert "Retry-After" in again.headers


def test_successful_login_resets_the_counter(client):
    assert _register(client).status_code == 201

    for _ in range(4):
        assert _login(client, "wrong-password").status_code == 401

    # The 4th failure is below the limit, so the right password still works
    # and must clear the email+IP counter.
    ok = _login(client, PASSWORD)
    assert ok.status_code == 200, ok.text

    # Another 4 failures would have crossed the limit without the reset.
    for _ in range(4):
        assert _login(client, "wrong-password").status_code == 401
    assert _login(client, PASSWORD).status_code == 200


def test_other_ip_is_not_locked_out(client):
    assert _register(client).status_code == 201
    for _ in range(5):
        assert _login(client, "wrong-password", headers=IP_A).status_code == 401
    assert _login(client, PASSWORD, headers=IP_A).status_code == 429

    # Same real user, different network: still works.
    assert _login(client, PASSWORD, headers=IP_B).status_code == 200
    # And a wrong password from that other IP is a plain 401, not a lock.
    assert _login(client, "wrong-password", headers=IP_B).status_code == 401


def test_unknown_email_looks_exactly_like_a_wrong_password(client):
    assert _register(client).status_code == 201
    real = _login(client, "wrong-password")
    fake = _login(client, "wrong-password", email="nobody@leadcrafttest.com")
    assert real.status_code == fake.status_code == 401
    assert real.json() == fake.json()


def test_register_is_capped_per_ip(client):
    for i in range(5):
        res = _register(client, email=f"bulk{i}@leadcrafttest.com")
        assert res.status_code == 201, res.text

    blocked = _register(client, email="bulk5@leadcrafttest.com")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_throttle_rows_store_hashes_only(client, tmp_path):
    assert _register(client).status_code == 201
    for _ in range(3):
        assert _login(client, "wrong-password").status_code == 401

    conn = sqlite3.connect(tmp_path / "limits.db")
    keys = [row[0] for row in conn.execute("select key_hash from auth_throttles")]
    conn.close()

    assert keys, "expected throttle rows"
    for key in keys:
        assert len(key) == 64
        assert EMAIL not in key
        assert "203.0.113.10" not in key
