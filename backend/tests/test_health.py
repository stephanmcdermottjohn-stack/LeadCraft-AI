"""Phase 1 gate: app boots, health endpoint works, schema creates all 6 tables."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import (
    Base,
    ClientSettings,
    ContentPost,
    Conversation,
    Lead,
    Message,
    User,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    # Force a deterministic "no credentials" state regardless of machine env.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    # get_settings is lru_cached; clear so the new env is picked up.
    from app import config, db

    config.get_settings.cache_clear()
    # Rebind engine/session to the test database.
    db.engine = db.create_engine_for_current_settings()
    db.SessionLocal = db.sessionmaker(bind=db.engine, autoflush=False, expire_on_commit=False, future=True)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["integrations"]["anthropic_configured"] is False
    assert body["integrations"]["whatsapp_configured"] is False


def test_schema_has_all_six_tables(client):
    from sqlalchemy import inspect

    inspector = inspect(client.app.state.db_engine)
    tables = set(inspector.get_table_names())
    expected = {"users", "clients_settings", "content_posts", "leads", "conversations", "messages"}
    assert expected <= tables
