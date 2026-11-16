"""Auth gate: register → login → me; wrong password and duplicate email rejected;
passwords are stored hashed (never plaintext)."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    from app import config, db

    config.get_settings.cache_clear()
    db.engine = db.create_engine_for_current_settings()
    db.SessionLocal = db.sessionmaker(bind=db.engine, autoflush=False, expire_on_commit=False, future=True)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_register_login_me_roundtrip(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Salon Noor", "email": "Noor@Example.com", "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["user"]["email"] == "noor@example.com"  # normalized lowercase
    assert body["user"]["plan_tier"] == "basic"
    assert "password" not in res.text and "hash" not in res.text

    login = client.post("/api/auth/login", json={"email": "noor@example.com", "password": "supersecret1"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["id"] == body["user"]["id"]

    # Empty clients_settings row created at registration.
    assert me.json()["user"]["business_name"] == "Salon Noor"


def test_login_rejects_wrong_password(client):
    client.post("/api/auth/register", json={"business_name": "X", "email": "x@y.com", "password": "correct1234"})
    bad = client.post("/api/auth/login", json={"email": "x@y.com", "password": "wrongpass99"})
    assert bad.status_code == 401


def test_duplicate_email_rejected(client):
    body = {"business_name": "X", "email": "dup@y.com", "password": "password123"}
    first = client.post("/api/auth/register", json=body)
    assert first.status_code == 201
    second = client.post("/api/auth/register", json=body)
    assert second.status_code == 409


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_password_stored_hashed(client, tmp_path):
    client.post("/api/auth/register", json={"business_name": "H", "email": "hash@y.com", "password": "plaintext-pw"})
    import sqlite3

    conn = sqlite3.connect(tmp_path / "auth.db")
    stored = conn.execute("select password_hash from users where email = 'hash@y.com'").fetchone()[0]
    conn.close()
    assert stored.startswith("pbkdf2_sha256$")
    assert "plaintext-pw" not in stored


def test_weak_password_rejected(client):
    res = client.post("/api/auth/register", json={"business_name": "W", "email": "w@y.com", "password": "short"})
    assert res.status_code == 422  # pydantic min_length=8
