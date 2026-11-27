"""P7 #1: custom landing pages built from validated, text-only blocks.

Zero network. Covers CRUD + slug rules, block validation and caps, tenant
isolation, role gates (viewer/agent), draft 404 vs published public shape,
capture through ``page_slug`` (including the workspace-mismatch guard), and the
20-page workspace cap.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'pages.db'}")
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


def register(client, email="pages@leadcrafttest.com", business_name="Gulberg Salon", slug=None):
    res = client.post(
        "/api/auth/register",
        json={"business_name": business_name, "email": email, "password": "supersecret1"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    if slug:
        assert client.patch("/api/settings", json={"landing_slug": slug}, headers=headers).status_code == 200
    return headers


def invite(client, headers, email, role="agent"):
    res = client.post("/api/team/invite", json={"email": email, "role": role}, headers=headers)
    assert res.status_code == 201, res.text
    token = res.json()["member"]["invite_path"].split("invite=", 1)[1]
    return token


def accept(client, headers, token):
    res = client.post("/api/team/accept", json={"token": token}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["member"]


def _hero(heading="Bridal season is open", **over):
    return {"type": "hero", "heading": heading,
            "subheading": "Book a free consultation", "cta_label": "Get started",
            "image_url": "", **over}


def _page(slug="bridal-offer", title="Bridal offer", blocks=None, is_published=False):
    return {"slug": slug, "title": title,
            "blocks": blocks if blocks is not None else [_hero()],
            "is_published": is_published}


def test_crud_and_slug_rules(client):
    headers = register(client, slug="crud-salon")

    res = client.post("/api/pages", json=_page(), headers=headers)
    assert res.status_code == 201, res.text
    page = res.json()["page"]
    pid = page["id"]
    assert page["slug"] == "bridal-offer"
    assert page["public_path"] == "/p/bridal-offer"
    assert page["is_published"] is False
    assert page["blocks"][0]["type"] == "hero"

    # Slug rules: format, reserved words, and global uniqueness.
    assert client.post("/api/pages", json=_page(slug="Bad Slug"), headers=headers).status_code == 400
    assert client.post("/api/pages", json=_page(slug="-leading"), headers=headers).status_code == 400
    assert client.post("/api/pages", json=_page(slug="admin"), headers=headers).status_code == 400
    assert client.post("/api/pages", json=_page(slug="p"), headers=headers).status_code == 400
    assert client.post("/api/pages", json=_page(slug="bridal-offer"), headers=headers).status_code == 409

    # Empty title is refused on update.
    assert client.patch(f"/api/pages/{pid}", json={"title": "   "}, headers=headers).status_code == 400
    # Partial update keeps untouched fields.
    res = client.patch(
        f"/api/pages/{pid}",
        json={"title": "Bridal season", "is_published": True},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    updated = res.json()["page"]
    assert updated["title"] == "Bridal season" and updated["is_published"] is True
    assert updated["blocks"][0]["heading"] == "Bridal season is open"

    # List is workspace-scoped and shows the cap.
    listed = client.get("/api/pages", headers=headers).json()
    assert [p["id"] for p in listed["pages"]] == [pid]
    assert listed["limit"] == 20

    assert client.delete(f"/api/pages/{pid}", headers=headers).status_code == 204
    assert client.get("/api/pages", headers=headers).json()["pages"] == []
    assert client.patch(f"/api/pages/{pid}", json={"title": "gone"}, headers=headers).status_code == 404


def test_block_validation_and_caps(client):
    headers = register(client, slug="blocks-salon")

    def create(blocks):
        return client.post("/api/pages", json=_page(slug="block-test", blocks=blocks), headers=headers)

    # Hero heading is required; unknown block types and non-object blocks fail.
    assert create([{"type": "hero", "subheading": "x"}]).status_code == 400
    assert create([{"type": "video"}]).status_code == 400
    assert create(["not-a-block"]).status_code in (400, 422)  # pydantic rejects non-object early
    # Hard cap: 12 blocks.
    assert create([_hero()] * 13).status_code == 400
    # Features: 1..6 items, each title required.
    assert create([{"type": "features", "items": []}]).status_code == 400
    assert create([{"type": "features", "items": [{"title": f"F{i}"} for i in range(7)]}]).status_code == 400
    assert create([{"type": "features", "items": [{"body": "no title"}]}]).status_code == 400
    # FAQ: max 8 items; question + answer required.
    assert create([{"type": "faq", "items": [{"question": f"Q{i}", "answer": "a"} for i in range(9)]}]).status_code == 400
    assert create([{"type": "faq", "items": [{"question": "Q"}]}]).status_code == 400
    # Image URL must be https:// or a rooted path.
    assert create([_hero(image_url="javascript:alert(1)")]).status_code == 400
    assert create([_hero(image_url="https://cdn.example.com/x.png")]).status_code == 201

    # Unknown keys are dropped; HTML stays a plain string (React escapes it).
    client.delete(f"/api/pages/{client.get('/api/pages', headers=headers).json()['pages'][0]['id']}", headers=headers)
    res = client.post(
        "/api/pages",
        json=_page(slug="text-salon", blocks=[
            {"type": "text", "body": "<script>alert(1)</script>", "evil": "x"},
        ]),
        headers=headers,
    )
    assert res.status_code == 201, res.text
    block = res.json()["page"]["blocks"][0]
    assert block == {"type": "text", "heading": "", "body": "<script>alert(1)</script>"}
    assert "evil" not in block

    # All six block types accept a minimal valid body together.
    blocks = [
        _hero(),
        {"type": "text", "body": "About us"},
        {"type": "features", "items": [{"title": "Fast"}]},
        {"type": "testimonial", "quote": "Great", "author": "Ayesha"},
        {"type": "faq", "items": [{"question": "Open?", "answer": "Yes"}]},
        {"type": "cta", "heading": "Book now"},
    ]
    assert client.post("/api/pages", json=_page(slug="all-blocks", blocks=blocks), headers=headers).status_code == 201


def test_tenant_isolation(client):
    owner = register(client, email="owner@pagestenant.com", business_name="Owner", slug="tenant-a")
    other = register(client, email="other@pagestenant.com", business_name="Other", slug="tenant-b")

    pid = client.post("/api/pages", json=_page(slug="tenant-page"), headers=owner).json()["page"]["id"]
    assert client.get("/api/pages", headers=other).json()["pages"] == []
    assert client.patch(f"/api/pages/{pid}", json={"title": "hijack"}, headers=other).status_code == 404
    assert client.delete(f"/api/pages/{pid}", headers=other).status_code == 404
    assert client.patch(f"/api/pages/{pid}", json={"title": "ok"}, headers=owner).status_code == 200


def test_role_gates_viewer_and_agent(client):
    owner = register(client, email="owner@pagesroles.com", business_name="Owner", slug="roles-salon")
    pid = client.post("/api/pages", json=_page(slug="roles-page"), headers=owner).json()["page"]["id"]

    viewer = register(client, email="viewer@pagesroles.com", business_name="Viewer", slug="viewer-own")
    accept(client, viewer, invite(client, owner, "viewer@pagesroles.com", role="viewer"))
    assert client.get("/api/pages", headers=viewer).status_code == 200
    assert client.post("/api/pages", json=_page(slug="viewer-page"), headers=viewer).status_code == 403
    assert client.patch(f"/api/pages/{pid}", json={"title": "no"}, headers=viewer).status_code == 403
    assert client.delete(f"/api/pages/{pid}", headers=viewer).status_code == 403

    agent = register(client, email="agent@pagesroles.com", business_name="Agent", slug="agent-own")
    accept(client, agent, invite(client, owner, "agent@pagesroles.com", role="agent"))
    assert client.get("/api/pages", headers=agent).status_code == 200
    res = client.post("/api/pages", json=_page(slug="agent-page"), headers=agent)
    assert res.status_code == 403 and "business settings" in res.json()["detail"]
    assert client.patch(f"/api/pages/{pid}", json={"title": "no"}, headers=agent).status_code == 403


def test_public_page_draft_and_published(client):
    headers = register(client, slug="public-salon")
    res = client.post("/api/pages", json=_page(slug="draft-page"), headers=headers)
    pid = res.json()["page"]["id"]

    # Draft is invisible publicly.
    assert client.get("/api/public/pages/draft-page").status_code == 404

    client.patch(
        f"/api/pages/{pid}",
        json={"slug": "live-page", "is_published": True},
        headers=headers,
    )
    assert client.get("/api/public/pages/draft-page").status_code == 404
    body = client.get("/api/public/pages/live-page").json()
    assert body["slug"] == "live-page"
    assert body["title"] == "Bridal offer"
    assert body["blocks"][0]["type"] == "hero"
    assert body["business"]["name"] == "Gulberg Salon"
    assert body["capture"]["page_slug"] == "live-page"
    assert body["capture"]["business_slug"] == "public-salon"
    assert "limits" in body and "no_html" in body["limits"]
    # Only display fields: no email/phone/consent data of any lead.
    assert "leads" not in body and "email" not in body["business"]

    # Unpublishing hides it again.
    client.patch(f"/api/pages/{pid}", json={"is_published": False}, headers=headers)
    assert client.get("/api/public/pages/live-page").status_code == 404


def test_capture_via_page_slug(client):
    headers = register(client, slug="capture-salon")
    pid = client.post(
        "/api/pages",
        json=_page(slug="capture-page", is_published=True),
        headers=headers,
    ).json()["page"]["id"]

    # Custom page alone resolves the workspace.
    res = client.post(
        "/api/leads/capture",
        json={"page_slug": "capture-page", "name": "Ayesha", "phone": "03001234567", "consent": True},
    )
    assert res.status_code == 201, res.text
    leads = client.get("/api/leads", headers=headers).json()["leads"]
    assert len(leads) == 1
    assert leads[0]["metadata"]["landing_page"] == "capture-page"
    assert leads[0]["source"] == "landing_page"

    # Both slugs are fine when they belong to the same workspace.
    assert client.post(
        "/api/leads/capture",
        json={"slug": "capture-salon", "page_slug": "capture-page", "name": "B", "email": "b@x.com", "consent": True},
    ).status_code == 201

    # A custom page from another workspace cannot be mixed with this slug.
    other = register(client, email="other@capturepages.com", business_name="Other", slug="other-capture")
    client.post("/api/pages", json=_page(slug="other-page", is_published=True), headers=other)
    res = client.post(
        "/api/leads/capture",
        json={"slug": "capture-salon", "page_slug": "other-page", "name": "C", "phone": "0300", "consent": True},
    )
    assert res.status_code == 400 and "same workspace" in res.json()["detail"]

    # No slug at all -> 400; unknown/draft page -> 404.
    assert client.post(
        "/api/leads/capture", json={"name": "D", "phone": "0300", "consent": True}
    ).status_code == 400
    assert client.post(
        "/api/leads/capture", json={"page_slug": "nope", "name": "D", "phone": "0300", "consent": True}
    ).status_code == 404
    client.patch(f"/api/pages/{pid}", json={"is_published": False}, headers=headers)
    assert client.post(
        "/api/leads/capture", json={"page_slug": "capture-page", "name": "E", "phone": "0300", "consent": True}
    ).status_code == 404
    # Consent and contact requirements still apply on custom pages.
    client.patch(f"/api/pages/{pid}", json={"is_published": True}, headers=headers)
    assert client.post(
        "/api/leads/capture", json={"page_slug": "capture-page", "name": "F", "phone": "0300", "consent": False}
    ).status_code == 400
    assert client.post(
        "/api/leads/capture", json={"page_slug": "capture-page", "name": "G", "consent": True}
    ).status_code == 400


def test_page_cap_per_workspace(client):
    headers = register(client, slug="cap-salon")
    for i in range(20):
        res = client.post("/api/pages", json=_page(slug=f"cap-{i}"), headers=headers)
        assert res.status_code == 201, res.text
    res = client.post("/api/pages", json=_page(slug="cap-20"), headers=headers)
    assert res.status_code == 400 and "20" in res.json()["detail"]

    # Another workspace still has its own budget.
    other = register(client, email="other@cappages.com", business_name="Other", slug="cap-other")
    assert client.post("/api/pages", json=_page(slug="other-cap-0"), headers=other).status_code == 201
