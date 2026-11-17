"""P0 #2: ICP builder + explainable lead fit. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'icp.db'}")
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
def owner_headers(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "owner@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "gulberg-salon"}, headers=headers)
    return headers


_ICP = {
    "name": "Bridal buyer",
    "location": "Gulberg",
    "budget_min": 50000,
    "budget_max": 300000,
    "needs": "bridal makeup package",
    "preferred_services": "trial session",
}


def _capture(client, **overrides):
    body = {"slug": "gulberg-salon", "name": "Ayesha Khan", "phone": "03001234567", "consent": True,
            "intent_notes": "Bridal makeup for December wedding", "extra": {"budget": "150000"}}
    body.update(overrides)
    return client.post("/api/leads/capture", json=body)


def _first_lead(client, headers):
    return client.get("/api/leads", headers=headers).json()["leads"][0]


# --- CRUD + validation -----------------------------------------------------------

def test_icp_crud_and_tenant_isolation(client, owner_headers):
    res = client.post("/api/icp", json=_ICP, headers=owner_headers)
    assert res.status_code == 201, res.text
    profile = res.json()["profile"]
    assert profile["criteria"] == []

    res = client.patch(f"/api/icp/{profile['id']}", json={**_ICP, "criteria": ["Local bride"], "is_default": True},
                       headers=owner_headers)
    assert res.status_code == 200
    assert res.json()["profile"]["is_default"] is True

    # Cross-tenant: other user sees nothing, updates nothing.
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "icpother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.get("/api/icp", headers=oh).json()["profiles"] == []
    assert client.patch(f"/api/icp/{profile['id']}", json=_ICP, headers=oh).status_code == 404
    assert client.delete(f"/api/icp/{profile['id']}", headers=oh).status_code == 404
    # Owner delete works.
    assert client.delete(f"/api/icp/{profile['id']}", headers=owner_headers).status_code == 204
    assert client.get("/api/icp", headers=owner_headers).json()["profiles"] == []


def test_icp_validation(client, owner_headers):
    assert client.post("/api/icp", json={"name": ""}, headers=owner_headers).status_code == 422
    res = client.post("/api/icp", json={**_ICP, "budget_min": 100, "budget_max": 50}, headers=owner_headers)
    assert res.status_code == 400
    res = client.post("/api/icp", json={**_ICP, "business_type": "nonsense"}, headers=owner_headers)
    assert res.status_code == 400
    # Long criteria lists are capped, not rejected.
    res = client.post("/api/icp", json={**_ICP, "criteria": [f"c{i}" for i in range(20)]}, headers=owner_headers)
    assert res.status_code == 201
    assert len(res.json()["profile"]["criteria"]) == 12


def test_icp_default_flag_unique_per_user(client, owner_headers):
    a = client.post("/api/icp", json={**_ICP, "name": "A", "is_default": True}, headers=owner_headers).json()["profile"]
    b = client.post("/api/icp", json={**_ICP, "name": "B", "is_default": True}, headers=owner_headers).json()["profile"]
    profiles = client.get("/api/icp", headers=owner_headers).json()["profiles"]
    flags = {p["name"]: p["is_default"] for p in profiles}
    assert flags["A"] is False and flags["B"] is True  # latest default wins


def test_icp_templates_endpoint(client, owner_headers):
    body = client.get("/api/icp/templates").json()
    keys = [t["key"] for t in body["templates"]]
    assert keys == ["property", "education", "healthcare", "ecommerce", "recruitment", "saas",
                    "professional_services", "other"]


# --- matching --------------------------------------------------------------------

def test_fit_match_with_explanations(client, owner_headers):
    # Budget lives in template extras; enable the property template so the
    # capture whitelist accepts it.
    client.patch(
        "/api/settings",
        json={"business_type": "property", "show_property_fields": True},
        headers=owner_headers,
    )
    profile = client.post("/api/icp", json=_ICP, headers=owner_headers).json()["profile"]
    _capture(client, area="Gulberg")
    lead = _first_lead(client, owner_headers)
    res = client.post(f"/api/icp/{profile['id']}/match/{lead['id']}", headers=owner_headers)
    assert res.status_code == 200, res.text
    fit = res.json()["fit"]
    assert fit["grade"] in ("A", "B")
    statuses = {f["factor"]: f["status"] for f in fit["factors"]}
    assert statuses["needs"] in ("match", "partial")
    assert statuses["budget"] == "match"  # 150000 within 50k-300k
    assert statuses["location"] == "match"
    assert all("detail" in f for f in fit["factors"])  # every factor is explainable


def test_fit_unknowns_never_drag_score_down(client, owner_headers):
    # ICP with no budget range and no location -> only keyword factors score.
    profile = client.post("/api/icp", json={"name": "Sparse", "needs": "bridal makeup package"}, headers=owner_headers).json()["profile"]
    _capture(client)
    lead = _first_lead(client, owner_headers)
    fit = client.post(f"/api/icp/{profile['id']}/match/{lead['id']}", headers=owner_headers).json()["fit"]
    assert fit["score"] is not None
    statuses = {f["factor"]: f["status"] for f in fit["factors"]}
    assert statuses["location"] == "unknown" and statuses["budget"] == "unknown"
    assert statuses["needs"] in ("match", "partial")


def test_fit_no_signal_returns_unknown_grade(client, owner_headers):
    # ICP and lead share no evaluable information at all.
    profile = client.post("/api/icp", json={"name": "Empty ICP"}, headers=owner_headers).json()["profile"]
    _capture(client, intent_notes="", extra={})
    lead = _first_lead(client, owner_headers)
    fit = client.post(f"/api/icp/{profile['id']}/match/{lead['id']}", headers=owner_headers).json()["fit"]
    assert fit["score"] is None and fit["grade"] == ""


def test_fit_cross_tenant_404(client, owner_headers):
    profile = client.post("/api/icp", json=_ICP, headers=owner_headers).json()["profile"]
    _capture(client)
    lead = _first_lead(client, owner_headers)
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "icpm@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    # Other user's ICP against owner's lead -> lead 404.
    other_profile = client.post("/api/icp", json=_ICP, headers=oh).json()["profile"]
    assert client.post(f"/api/icp/{other_profile['id']}/match/{lead['id']}", headers=oh).status_code == 404
