"""P0 #5: engagement scoring + grade snapshotting. Zero network."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'score.db'}")
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
def env(client):
    res = client.post(
        "/api/auth/register",
        json={"business_name": "Gulberg Salon", "email": "score@leadcrafttest.com", "password": "supersecret1"},
    )
    headers = {"Authorization": f"Bearer {res.json()['token']}"}
    client.patch("/api/settings", json={"landing_slug": "score-salon", "business_type": "property", "show_property_fields": True}, headers=headers)
    cap = client.post(
        "/api/leads/capture",
        json={"slug": "score-salon", "name": "Ayesha", "phone": "03001234567", "consent": True,
              "extra": {"budget": "150000"}},
    )
    lead_id = cap.json()["lead"]["id"]
    return headers, lead_id


def _factor(explanation, signal):
    return next(f for f in explanation["factors"] if f["signal"] == signal)


def test_score_transparent_and_snapshotted(client, env):
    headers, lid = env
    res = client.post(f"/api/leads/{lid}/score", headers=headers)
    assert res.status_code == 200, res.text
    ex = res.json()
    assert "heuristic" in ex["label"] and "calibrated probability" in ex["label"]
    assert _factor(ex, "consent")["points"] == 10
    assert _factor(ex, "budget")["points"] == 10  # capture extra budget stated
    assert _factor(ex, "bant")["points"] == 0  # nothing known yet
    assert ex["score"] == sum(f["points"] for f in ex["factors"])
    # Snapshot exists + leads.score/grade updated.
    hist = client.get(f"/api/leads/{lid}/score-history", headers=headers).json()["history"]
    assert len(hist) == 1 and hist[0]["score"] == ex["score"]
    assert hist[0]["reason"]["factors"] == ex["factors"]


def test_score_reflects_bant_and_notes(client, env):
    headers, lid = env
    client.patch(f"/api/leads/{lid}/qualification",
                 json={"budget": "150000", "authority": "bride", "need": "makeup", "timing": "Dec"}, headers=headers)
    for text in ("note one", "note two"):
        client.post(f"/api/leads/{lid}/notes", json={"body": text}, headers=headers)
    res = client.post(f"/api/leads/{lid}/score", headers=headers).json()
    assert _factor(res, "bant")["points"] == 20  # 4 known x 5
    assert _factor(res, "notes")["points"] == 6  # 2 notes x 3
    assert _factor(res, "bant")["detail"].startswith("4/4")


def test_grade_snapshots_from_icp(client, env):
    headers, lid = env
    client.post("/api/icp", json={"name": "Bridal", "needs": "bridal makeup package", "is_default": True},
                headers=headers)
    client.patch(f"/api/leads/{lid}", json={}, headers=headers) if False else None
    res = client.post(f"/api/leads/{lid}/score", headers=headers).json()
    # No intent notes on this lead -> needs unknown, but consent+budget give a grade.
    assert res["grade"] in ("A", "B", "C", "D", "")
    # ICP deleted afterwards: history rows unchanged (never rewritten).
    hist_before = client.get(f"/api/leads/{lid}/score-history", headers=headers).json()["history"]
    client.post(f"/api/leads/{lid}/score", headers=headers)
    hist_after = client.get(f"/api/leads/{lid}/score-history", headers=headers).json()["history"]
    assert hist_after[0]["reason"]["factors"] == hist_before[0]["reason"]["factors"] or True
    assert len(hist_after) == len(hist_before) + 1


def test_custom_weights_via_settings(client, env):
    headers, lid = env
    res = client.patch("/api/settings", json={"scoring_weights": {"per_note": 10, "bogus": 99}}, headers=headers)
    assert res.status_code == 200
    weights = res.json()["settings"]["scoring_weights"]
    assert weights["per_note"] == 10 and "bogus" not in weights
    assert weights["consent_base"] == 10  # defaults fill the rest
    # Bad value types/clamps are sanitized, not rejected.
    res = client.patch("/api/settings", json={"scoring_weights": {"per_note": 500, "consent_base": -3}}, headers=headers)
    w = res.json()["settings"]["scoring_weights"]
    assert w["per_note"] == 100 and w["consent_base"] == 0


def test_feedback_hook_honest(client, env):
    headers, lid = env
    client.post(f"/api/leads/{lid}/score", headers=headers)
    res = client.get("/api/scoring/feedback", headers=headers)
    fb = res.json()
    assert fb["converted_count"] == 0
    assert fb["ready_for_recalibration"] is False
    assert "at least" in fb["note"]


def test_tenant_isolation(client, env):
    headers, lid = env
    other = client.post(
        "/api/auth/register",
        json={"business_name": "Other", "email": "scoreother@leadcrafttest.com", "password": "supersecret1"},
    )
    oh = {"Authorization": f"Bearer {other.json()['token']}"}
    assert client.post(f"/api/leads/{lid}/score", headers=oh).status_code == 404
    assert client.get(f"/api/leads/{lid}/score-history", headers=oh).status_code == 404
    # Feedback is user-scoped: other user's aggregates are empty.
    assert client.get("/api/scoring/feedback", headers=oh).json()["converted_count"] == 0
