"""Phase 2 gate: content generation (mock, zero network), scheduling, due-post
worker, and the Gemini adapter contract with a mocked transport (zero real
network calls — the adapter is only allowed live once a key exists)."""
import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations import llm
from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'content.db'}")
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
def auth_headers(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Salon Noor", "email": "noor@leadcrafttest.com", "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_generate_requires_auth(client):
    assert client.post("/api/content/generate", json={}).status_code == 401


def test_generate_mock_provider_zero_network(client, auth_headers, monkeypatch):
    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        raise AssertionError("mock provider must not touch the network")

    monkeypatch.setattr(httpx, "post", boom)
    res = client.post(
        "/api/content/generate",
        json={"platform": "facebook", "tone": "friendly", "count": 3},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["provider"] == "mock"
    assert len(body["options"]) == 3
    assert all(opt.startswith("[MOCK]") for opt in body["options"])
    assert "[MOCK]" in body["notice"] or "mock" in body["notice"].lower()
    assert calls == []


def test_generate_uses_client_settings_not_business_name_only(client, auth_headers):
    # Personalization: the prompt is built from clients_settings; verify the
    # mock templates actually embed the configured niche/area.
    client.patch(
        "/api/settings",
        json={"niche": "bridal makeup", "target_area": "Gulberg Lahore", "brand_voice": "warm"},
        headers=auth_headers,
    )
    res = client.post("/api/content/generate", json={"count": 3}, headers=auth_headers)
    assert res.status_code == 200
    text = " ".join(res.json()["options"])
    assert "bridal makeup" in text
    assert "Gulberg Lahore" in text


def test_settings_roundtrip(client, auth_headers):
    empty = client.get("/api/settings", headers=auth_headers).json()["settings"]
    assert empty == {"niche": "", "target_area": "", "brand_voice": ""}
    res = client.patch(
        "/api/settings",
        json={"niche": "salon", "target_area": "DHA", "brand_voice": "premium"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["settings"]["brand_voice"] == "premium"
    assert client.get("/api/settings", headers=auth_headers).json()["settings"]["niche"] == "salon"
    assert client.get("/api/settings").status_code == 401


def test_generate_rejects_bad_platform(client, auth_headers):
    res = client.post("/api/content/generate", json={"platform": "myspace"}, headers=auth_headers)
    assert res.status_code == 400


def test_schedule_and_list(client, auth_headers):
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).isoformat()
    res = client.post(
        "/api/content/schedule",
        json={"content_text": "Test post body", "platform": "instagram", "scheduled_at": future},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    post = res.json()["post"]
    assert post["status"] == "scheduled"

    posts = client.get("/api/content/posts", headers=auth_headers).json()["posts"]
    assert len(posts) == 1
    assert posts[0]["platform"] == "instagram"

    # Other users must not see it.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "other@leadcrafttest.com", "password": "supersecret1"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/content/posts", headers=other_headers).json()["posts"] == []


def test_worker_flips_due_posts(client, auth_headers):
    from app.db import SessionLocal
    from app.workers.content_worker import run_due_posts_pass

    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
    for when in (past, future):
        res = client.post(
            "/api/content/schedule",
            json={"content_text": "b", "platform": "facebook", "scheduled_at": when.isoformat()},
            headers=auth_headers,
        )
        assert res.status_code == 201

    flipped = run_due_posts_pass(SessionLocal())
    assert flipped == 1
    statuses = {p["status"] for p in client.get("/api/content/posts", headers=auth_headers).json()["posts"]}
    assert statuses == {"scheduled", "ready_to_publish"}


def test_gemini_adapter_contract_mocked_transport(monkeypatch):
    """Contract test: URL shape, auth header, response parsing — no real network."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key_header"] = request.headers.get("x-goog-api-key")
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Option one\n---\nOption two"}]}}]},
        )

    monkeypatch.setattr(
        httpx, "post",
        lambda url, **kw: handler(httpx.Request("POST", url, headers=kw.get("headers"), json=kw.get("json"))),
    )
    text = llm.gemini_generate_text("prompt", "fake-key", "gemini-test-model")
    assert "/v1beta/models/gemini-test-model:generateContent" in seen["url"]
    assert seen["key_header"] == "fake-key"
    assert text == "Option one\n---\nOption two"


def test_gemini_adapter_never_calls_network_without_key(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no network call allowed without credentials")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(llm.LLMError) as exc_info:
        llm.gemini_generate_text("prompt", "", "gemini-test-model")
    assert exc_info.value.code == "missing-credentials"
    assert "aistudio.google.com" in exc_info.value.message


def test_gemini_adapter_maps_errors(monkeypatch):
    def make(status):
        return lambda url, **kw: httpx.Response(status, json={"error": {"message": "x"}})

    monkeypatch.setattr(httpx, "post", make(429))
    with pytest.raises(llm.LLMError) as e429:
        llm.gemini_generate_text("p", "k", "m")
    assert e429.value.code == "rate-limited"

    monkeypatch.setattr(httpx, "post", make(403))
    with pytest.raises(llm.LLMError) as e403:
        llm.gemini_generate_text("p", "k", "m")
    assert e403.value.code == "invalid-credentials"


def test_parse_options_splits_and_caps():
    assert llm.parse_options("a\n---\nb\n---\nc", 2) == ["a", "b"]
    with pytest.raises(llm.LLMError):
        llm.parse_options("", 1)
