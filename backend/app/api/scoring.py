"""Engagement scoring endpoints (roadmap P0 #5). Lead-scoped routes are
tenant-checked (cross-tenant → 404); feedback is user-scoped aggregates only.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, IcpProfile, Lead, LeadNote, LeadQualification, LeadScoreHistory, User
from app.services import scoring as svc

leads_router = APIRouter(prefix="/api/leads")
scoring_router = APIRouter(prefix="/api/scoring")


def _lead_metadata(lead: Lead) -> dict:
    try:
        parsed = json.loads(lead.metadata_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def _default_icp(db: Session, user_id: int) -> IcpProfile | None:
    row = db.scalar(
        select(IcpProfile).where(IcpProfile.user_id == user_id).order_by(IcpProfile.is_default.desc(), IcpProfile.created_at.desc())
    )
    return row


def _icp_public(p: IcpProfile) -> dict:
    from app.api.icp import _public  # reuse the exact same serialization

    return _public(p)


def _get_owned_lead(db: Session, lead_id: int, user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


def _latest_snapshots(db: Session, user: User) -> list[dict]:
    """Latest score snapshot per lead (for the conversion-feedback hook)."""
    rows = db.scalars(
        select(LeadScoreHistory)
        .where(LeadScoreHistory.user_id == user.id)
        .order_by(LeadScoreHistory.lead_id, LeadScoreHistory.created_at.asc())
    ).all()
    latest: dict[int, dict] = {}
    for r in rows:
        latest[r.lead_id] = {"score": r.score, "lead_id": r.lead_id}
    if not latest:
        return []
    leads = {l.id: l for l in db.scalars(select(Lead).where(Lead.user_id == user.id)).all()}
    out = []
    for lead_id, snap in latest.items():
        lead = leads.get(lead_id)
        if lead is None:
            continue
        out.append({**snap, "converted": lead.status == "converted"})
    return out


class ScoreBody(BaseModel):
    # Optional weight override just for THIS computation (snapshot keeps it in
    # reason_json). Stored weights stay unchanged unless edited via settings.
    weights: dict[str, int] | None = None


@leads_router.post("/{lead_id}/score")
def score_lead(
    lead_id: int,
    body: ScoreBody | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lead = _get_owned_lead(db, lead_id, user)
    settings_row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    weights = svc.sanitize_weights(body.weights) if body and body.weights else svc.effective_weights(settings_row)
    notes_count = db.scalar(select(func.count()).select_from(LeadNote).where(LeadNote.lead_id == lead.id)) or 0
    qual_row = db.scalar(select(LeadQualification).where(LeadQualification.lead_id == lead.id))
    bant_known = 0
    if qual_row:
        bant_known = sum(
            1 for d in ("budget", "authority", "need", "timing")
            if getattr(qual_row, f"{d}_confidence") == "known" and getattr(qual_row, f"{d}_value").strip()
        )
    budget_stated = bool(str(_lead_metadata(lead).get("budget", "") or "").strip())
    computed = svc.compute(
        stage=lead.lifecycle_stage, notes_count=notes_count,
        bant_known=bant_known, budget_stated=budget_stated, weights=weights,
    )
    icp_profile = _default_icp(db, user.id)
    grade = ""
    if icp_profile is not None:
        from app.services.icp import match_lead

        grade = match_lead(
            _icp_public(icp_profile),
            {"area": lead.area, "intent_notes": lead.intent_notes, "metadata": _lead_metadata(lead)},
        ).get("grade", "")
    snap = LeadScoreHistory(
        lead_id=lead.id, user_id=user.id, score=computed["score"], grade=grade,
        reason_json=json.dumps({"label": computed["label"], "weights": weights, "factors": computed["factors"]}),
    )
    # Current-value columns: latest snapshot wins (history keeps the past).
    lead.score = computed["score"]
    lead.grade = grade
    db.add(snap)
    db.commit()
    history_count = db.scalar(
        select(func.count()).select_from(LeadScoreHistory).where(LeadScoreHistory.lead_id == lead.id)
    )
    return {
        "score": computed["score"],
        "grade": grade,
        "label": computed["label"],
        "factors": computed["factors"],
        "weights_used": weights,
        "history_count": history_count or 0,
    }


@leads_router.get("/{lead_id}/score-history")
def score_history(
    lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    lead = _get_owned_lead(db, lead_id, user)
    rows = db.scalars(
        select(LeadScoreHistory)
        .where(LeadScoreHistory.lead_id == lead.id)
        .order_by(LeadScoreHistory.created_at.desc(), LeadScoreHistory.id.desc())
    ).all()
    return {
        "history": [
            {
                "id": r.id,
                "score": r.score,
                "grade": r.grade,
                "reason": svc.parse_reason(r.reason_json),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@scoring_router.get("/feedback")
def feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Recalibration hook: honest conversion-outcome stats. Changes nothing."""
    return svc.conversion_feedback(_latest_snapshots(db, user))
