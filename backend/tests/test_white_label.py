"""P3 #2: white-label branding - owner-entered presentation fields, validation,
public landing exposure, tenant isolation. Zero network.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'whitelabel.db'}")
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


def register(client, email="brand@leadcrafttest.com", slug="brand-salon"):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": email, "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": slug}, headers=headers)
    return headers


def test_branding_roundtrip_and_public_landing(client):
    headers = register(client)
    body = client.get("/api/settings", headers=headers).json()["settings"]
    # Defaults are honest, not pre-filled with a fake brand.
    assert body["brand_name"] == "" and body["primary_color"] == ""
    assert body["hide_platform_brand"] is False
    assert "Presentation only" in body["white_label_note"]

    res = client.patch(
        "/api/settings",
        json={
            "brand_name": "Glow Studio",
            "logo_url": "https://cdn.example.com/logo.png",
            "primary_color": "#0EA5E9",
            "support_email": "help@glowstudio.pk",
            "footer_text": "Glow Studio · Lahore",
            "hide_platform_brand": True,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    saved = res.json()["settings"]
    assert saved["brand_name"] == "Glow Studio"
    assert saved["primary_color"] == "#0ea5e9"  # normalised lowercase
    assert saved["hide_platform_brand"] is True

    public = client.get("/api/public/landing/brand-salon").json()
    assert public["brand_name"] == "Glow Studio"
    assert public["logo_url"] == "https://cdn.example.com/logo.png"
    assert public["primary_color"] == "#0ea5e9"
    assert public["support_email"] == "help@glowstudio.pk"
    assert public["footer_text"] == "Glow Studio · Lahore"
    assert public["hide_platform_brand"] is True
    # Public config still carries no owner personal data.
    assert "owner" not in public and "email" not in public

    # Clearing works (empty string = clear), and the display falls back to the
    # business name in the UI (backend returns the raw empty string).
    cleared = client.patch(
        "/api/settings",
        json={"brand_name": "", "logo_url": "", "primary_color": "", "footer_text": ""},
        headers=headers,
    ).json()["settings"]
    assert cleared["brand_name"] == "" and cleared["primary_color"] == ""
    assert client.get("/api/public/landing/brand-salon").json()["brand_name"] == ""


def test_branding_validation(client):
    headers = register(client, email="brand2@leadcrafttest.com", slug="brand-two")
    cases = [
        ({"primary_color": "blue"}, "hex colour"),
        ({"primary_color": "#12345"}, "hex colour"),
        ({"logo_url": "javascript:alert(1)"}, "http(s)"),
        ({"logo_url": "data:image/svg+xml;base64,abc"}, "http(s)"),
        ({"logo_url": "https://x.test/a b.png"}, "spaces"),
        ({"support_email": "not-an-email"}, "valid email"),
    ]
    for payload, needle in cases:
        res = client.patch("/api/settings", json=payload, headers=headers)
        assert res.status_code == 400, payload
        assert needle in res.json()["detail"]
    # Relative paths are allowed (self-hosted assets).
    assert client.patch(
        "/api/settings", json={"logo_url": "/assets/logo.png"}, headers=headers
    ).status_code == 200


def test_branding_is_tenant_scoped(client):
    a = register(client, email="branda@leadcrafttest.com", slug="brand-a")
    b = register(client, email="brandb@leadcrafttest.com", slug="brand-b")
    client.patch("/api/settings", json={"brand_name": "A Brand", "hide_platform_brand": True}, headers=a)
    pa = client.get("/api/public/landing/brand-a").json()
    pb = client.get("/api/public/landing/brand-b").json()
    assert pa["brand_name"] == "A Brand" and pa["hide_platform_brand"] is True
    assert pb["brand_name"] == "" and pb["hide_platform_brand"] is False
    # B's private settings never show A's brand.
    assert client.get("/api/settings", headers=b).json()["settings"]["brand_name"] == ""
    # Public config needs auth? No - but writes do.
    assert client.patch("/api/settings", json={"brand_name": "x"}).status_code == 401
