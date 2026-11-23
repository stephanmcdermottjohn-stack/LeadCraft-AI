"""Security hardening checks (security pass).

Covers the production signing-key guard and the fact that auth reads the
secret through Settings (so `backend/.env` works even when it is not exported
into the process environment).
"""
import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import create_app
from app.services import auth_service


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    yield
    config.get_settings.cache_clear()


def _prepare(tmp_path, monkeypatch, *, secret: str, environment: str) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'security.db'}")
    monkeypatch.setenv("SECRET_KEY", secret)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("APP_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    config.get_settings.cache_clear()
    db.engine = db.create_engine_for_current_settings()
    db.SessionLocal = db.sessionmaker(bind=db.engine, autoflush=False, expire_on_commit=False, future=True)


def test_production_refuses_missing_or_default_secret(tmp_path, monkeypatch):
    for secret in ("", auth_service.DEV_SECRET, "   "):
        _prepare(tmp_path, monkeypatch, secret=secret, environment="production")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app()


def test_production_boots_with_strong_secret(tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch, secret="x" * 64, environment="production")
    app = create_app()
    assert app.title == "leadcraft-ai"


def test_auth_reads_secret_from_settings_and_rejects_bad_signature(tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch, secret="settings-only-secret", environment="development")
    # A key present only in .env/Settings still signs and verifies tokens.
    assert auth_service._secret_key() == "settings-only-secret"

    app = create_app()
    with TestClient(app) as client:
        reg = client.post(
            "/api/auth/register",
            json={
                "business_name": "Security Salon",
                "email": "security@leadcrafttest.com",
                "password": "supersecret1",
            },
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["token"]
        uid = reg.json()["user"]["id"]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        # Same payload, forged signature -> rejected (HMAC compare, not parsing).
        payload = base64.urlsafe_b64encode(
            json.dumps({"uid": uid, "exp": int(time.time()) + 600}).encode()
        ).decode().rstrip("=")
        forged = f"{payload}.{'0' * 64}"
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
