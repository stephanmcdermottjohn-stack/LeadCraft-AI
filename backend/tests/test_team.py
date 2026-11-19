"""P3 #1: team members & roles - invite/accept, workspace scoping, write gates.

Zero network. Each test gets a fresh sqlite database.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'team.db'}")
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


def register(client, email, business_name="Gulberg Salon", slug=None):
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
    body = res.json()["member"]
    token = body["invite_path"].split("invite=", 1)[1]
    return body, token


def accept(client, headers, token):
    res = client.post("/api/team/accept", json={"token": token}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["member"]


def capture(client, slug="team-salon", name="Ayesha"):
    res = client.post(
        "/api/leads/capture",
        json={"slug": slug, "name": name, "phone": "03001112222", "consent": True},
    )
    assert res.status_code == 201, res.text
    return res.json()["lead"]["id"]


def test_invite_accept_member_shares_workspace_scope(client):
    owner = register(client, "owner@teamtest.com", slug="team-salon")
    lead_id = capture(client)
    # Existing account (no leads of its own) -> pending invite, accepted by token.
    member_headers = register(client, "agent@teamtest.com", business_name="Agent Personal", slug="agent-personal")
    member_row, token = invite(client, owner, "agent@teamtest.com", role="agent")
    assert member_row["status"] == "invited" and member_row["member_user_id"] is not None
    accepted = accept(client, member_headers, token)
    assert accepted["status"] == "active" and accepted["role"] == "agent"

    me = client.get("/api/auth/me", headers=member_headers).json()["user"]
    assert me["role"] == "agent"
    assert me["email"] == "agent@teamtest.com"
    assert me["business_name"] == "Gulberg Salon"
    assert me["is_workspace_member"] is True
    assert me["workspace_owner_email"] == "owner@teamtest.com"

    # Member reads the owner's workspace data (existing scoping inherited).
    leads = client.get("/api/leads", headers=member_headers).json()["leads"]
    assert [l["id"] for l in leads] == [lead_id]
    # Agent may write operational data.
    assert client.patch(
        f"/api/leads/{lead_id}/status", json={"status": "contacted"}, headers=member_headers
    ).status_code == 200
    assert client.get("/api/leads", headers=owner).json()["leads"][0]["status"] == "contacted"
    # Token is single-use.
    assert client.post("/api/team/accept", json={"token": token}, headers=member_headers).status_code == 404
    # Team list: member sees roles but no invite secrets.
    team = client.get("/api/team", headers=member_headers).json()
    assert team["my_role"] == "agent"
    assert team["members"][0]["invite_path"] is None


def test_viewer_is_read_only(client):
    owner = register(client, "owner@viewertest.com", slug="viewer-salon")
    lead_id = capture(client, slug="viewer-salon")
    viewer_headers = register(client, "viewer@viewertest.com", slug="viewer-personal")
    _, token = invite(client, owner, "viewer@viewertest.com", role="viewer")
    accept(client, viewer_headers, token)

    assert client.get("/api/leads", headers=viewer_headers).status_code == 200
    assert client.get("/api/settings", headers=viewer_headers).status_code == 200
    assert client.get(f"/api/leads/{lead_id}/timeline", headers=viewer_headers).status_code == 200

    res = client.patch(f"/api/leads/{lead_id}/status", json={"status": "contacted"}, headers=viewer_headers)
    assert res.status_code == 403 and "read-only" in res.json()["detail"]
    assert client.post(f"/api/leads/{lead_id}/notes", json={"text": "hi"}, headers=viewer_headers).status_code == 403
    assert client.patch("/api/settings", json={"niche": "x"}, headers=viewer_headers).status_code == 403
    assert client.post("/api/reviews", json={"lead_id": lead_id}, headers=viewer_headers).status_code == 403


def test_agent_cannot_change_business_config(client):
    owner = register(client, "owner@agenttest.com", slug="agent-salon")
    lead_id = capture(client, slug="agent-salon")
    agent_headers = register(client, "worker@agenttest.com", slug="agent-personal")
    _, token = invite(client, owner, "worker@agenttest.com", role="agent")
    accept(client, agent_headers, token)

    # Operational writes stay open.
    assert client.patch(
        f"/api/leads/{lead_id}/status", json={"status": "contacted"}, headers=agent_headers
    ).status_code == 200
    # Business configuration is manager+ only.
    res = client.patch("/api/settings", json={"niche": "bridal"}, headers=agent_headers)
    assert res.status_code == 403 and "business settings" in res.json()["detail"]
    assert client.put(
        "/api/campaign-spend", json={"campaign": "Eid", "spend": 100}, headers=agent_headers
    ).status_code == 403
    assert client.get("/api/settings", headers=agent_headers).status_code == 200


def test_team_management_permissions_and_removal(client):
    owner = register(client, "owner@mgmttest.com", slug="mgmt-salon")
    lead_id = capture(client, slug="mgmt-salon")

    admin_headers = register(client, "admin@mgmttest.com", slug="admin-personal")
    admin_row, admin_token = invite(client, owner, "admin@mgmttest.com", role="admin")
    accept(client, admin_headers, admin_token)

    agent_headers = register(client, "staff@mgmttest.com", slug="staff-personal")
    agent_row, agent_token = invite(client, owner, "staff@mgmttest.com", role="agent")
    accept(client, agent_headers, agent_token)

    # Admin can invite, agent cannot.
    assert client.post(
        "/api/team/invite", json={"email": "extra@mgmttest.com", "role": "viewer"}, headers=admin_headers
    ).status_code == 201
    assert client.post(
        "/api/team/invite", json={"email": "nope@mgmttest.com", "role": "viewer"}, headers=agent_headers
    ).status_code == 403
    # Cannot change your own role, or the owner's (owner is not a member row).
    assert client.patch(
        f"/api/team/{admin_row['id']}", json={"role": "viewer"}, headers=admin_headers
    ).status_code == 400
    # Owner changes agent -> viewer: next request is read-only immediately.
    assert client.patch(
        f"/api/team/{agent_row['id']}", json={"role": "viewer"}, headers=owner
    ).status_code == 200
    assert client.patch(
        f"/api/leads/{lead_id}/status", json={"status": "contacted"}, headers=agent_headers
    ).status_code == 403
    # Cross-workspace admin cannot touch this member row.
    other = register(client, "other@mgmttest.com", slug="other-salon")
    assert client.patch(
        f"/api/team/{agent_row['id']}", json={"role": "agent"}, headers=other
    ).status_code == 404
    assert client.delete(f"/api/team/{agent_row['id']}", headers=other).status_code == 404
    # Remove: access reverts to the (empty) personal workspace.
    assert client.delete(f"/api/team/{agent_row['id']}", headers=owner).status_code == 204
    assert client.get("/api/leads", headers=agent_headers).json()["leads"] == []
    me = client.get("/api/auth/me", headers=agent_headers).json()["user"]
    assert me["role"] == "owner" and me["is_workspace_member"] is False
    # Removed members cannot be patched as if active.
    assert client.patch(
        f"/api/team/{agent_row['id']}", json={"role": "agent"}, headers=owner
    ).status_code == 400
    # Admin cannot remove themselves.
    assert client.delete(f"/api/team/{admin_row['id']}", headers=admin_headers).status_code == 400


def test_invite_refuses_account_with_own_leads(client):
    owner = register(client, "owner@conflicttest.com", slug="conflict-salon")
    register(client, "busy@conflicttest.com", business_name="Busy Co", slug="busy-co")
    capture(client, slug="busy-co", name="Their Lead")
    res = client.post(
        "/api/team/invite", json={"email": "busy@conflicttest.com", "role": "agent"}, headers=owner
    )
    assert res.status_code == 409 and "own leads" in res.json()["detail"]


def test_invite_validation_and_accept_gates(client):
    owner = register(client, "owner@gatetest.com", slug="gate-salon")
    # Role validation / self invite.
    assert client.post(
        "/api/team/invite", json={"email": "x@gatetest.com", "role": "owner"}, headers=owner
    ).status_code == 400
    assert client.post(
        "/api/team/invite", json={"email": "owner@gatetest.com", "role": "agent"}, headers=owner
    ).status_code == 400
    # Fresh email: invite before the account exists, then register + accept.
    _, token = invite(client, owner, "fresh@gatetest.com", role="manager")
    fresh = register(client, "fresh@gatetest.com", slug="fresh-personal")
    accept(client, fresh, token)
    me = client.get("/api/auth/me", headers=fresh).json()["user"]
    assert me["role"] == "manager" and me["is_workspace_member"] is True
    # Wrong email cannot use someone else's token.
    _, token2 = invite(client, owner, "invited@gatetest.com", role="agent")
    stranger = register(client, "stranger@gatetest.com", slug="stranger-personal")
    res = client.post("/api/team/accept", json={"token": token2}, headers=stranger)
    assert res.status_code == 403 and "different email" in res.json()["detail"]
    # Bad token + auth gates.
    assert client.post("/api/team/accept", json={"token": "nope-nope-nope"}, headers=stranger).status_code == 404
    assert client.get("/api/team").status_code == 401
    assert client.post("/api/team/accept", json={"token": token2}).status_code == 401
    # Re-invite rotates the token: the old link stops working, the new one works.
    _, rotated = invite(client, owner, "invited@gatetest.com", role="agent")
    assert rotated != token2
    invited = register(client, "invited@gatetest.com", slug="invited-personal")
    assert client.post("/api/team/accept", json={"token": token2}, headers=invited).status_code == 404
    accept(client, invited, rotated)
