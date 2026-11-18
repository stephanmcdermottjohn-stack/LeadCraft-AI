"""Nurture workflow endpoints (P1 #2). All user-scoped: campaigns,
enrollments and suppressions are tenant-checked (cross-tenant → 404).

No endpoint sends any message: due touches surface as the lead's
next_action + timeline activity. The scheduler loop (and POST
/api/nurture/process-due for on-demand runs) drives progression.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Lead, NurtureCampaign, NurtureEnrollment, NurtureSuppression, User
from app.services import nurture as svc

router = APIRouter(prefix="/api/nurture")


class StepIn(BaseModel):
    day_offset: int
    message: str = Field(min_length=1, max_length=500)


class CampaignBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    steps: list[StepIn]
    active: bool = True


class EnrollBody(BaseModel):
    lead_id: int


class SuppressionBody(BaseModel):
    value: str = Field(min_length=3, max_length=320)
    reason: str = Field(default="", max_length=200)


def _campaign_public(c: NurtureCampaign, db: Session | None = None) -> dict:
    try:
        steps = json.loads(c.steps_json or "[]")
    except ValueError:
        steps = []
    out = {
        "id": c.id,
        "name": c.name,
        "steps": steps,
        "active": bool(c.active),
    }
    if db is not None:
        out["metrics"] = svc.metrics(db, c)
    return out


def _enrollment_public(e: NurtureEnrollment, lead: Lead | None) -> dict:
    return {
        "id": e.id,
        "campaign_id": e.campaign_id,
        "lead_id": e.lead_id,
        "lead_name": lead.name if lead else "",
        "status": e.status,
        "steps_total": e.steps_total,
        "current_step": e.current_step,
        "next_step_at": e.next_step_at.isoformat() if e.next_step_at else None,
        "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
    }


def _get_owned_campaign(db: Session, campaign_id: int, user: User) -> NurtureCampaign:
    row = db.get(NurtureCampaign, campaign_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return row


def _get_owned_enrollment(db: Session, enrollment_id: int, user: User) -> NurtureEnrollment:
    row = db.get(NurtureEnrollment, enrollment_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Enrollment not found.")
    return row


# --- campaigns ----------------------------------------------------------------

@router.get("/campaigns")
def list_campaigns(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(NurtureCampaign).where(NurtureCampaign.user_id == user.id).order_by(NurtureCampaign.created_at.desc())
    ).all()
    return {"campaigns": [_campaign_public(c, db) for c in rows]}


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        steps = svc.parse_steps([s.model_dump() for s in body.steps])
    except svc.StepError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = NurtureCampaign(user_id=user.id, name=body.name.strip(), steps_json=json.dumps(steps), active=body.active)
    db.add(row)
    db.commit()
    return {"campaign": _campaign_public(row)}


@router.patch("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: int, body: CampaignBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    row = _get_owned_campaign(db, campaign_id, user)
    try:
        steps = svc.parse_steps([s.model_dump() for s in body.steps])
    except svc.StepError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row.name = body.name.strip()
    row.steps_json = json.dumps(steps)
    row.active = body.active
    db.commit()
    return {"campaign": _campaign_public(row, db)}


@router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    row = _get_owned_campaign(db, campaign_id, user)
    any_enrollment = db.scalar(select(NurtureEnrollment.id).where(NurtureEnrollment.campaign_id == row.id))
    if any_enrollment is not None:
        # Any enrollment (even stopped/completed) keeps the campaign: deleting
        # it would orphan enrollment history. Owners deactivate instead.
        raise HTTPException(status_code=400, detail="Campaign has enrollments (any status) - deactivate it instead of deleting.")
    db.delete(row)
    db.commit()


# --- enrollment ----------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/enroll", status_code=201)
def enroll_lead(
    campaign_id: int, body: EnrollBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    campaign = _get_owned_campaign(db, campaign_id, user)
    if not campaign.active:
        raise HTTPException(status_code=400, detail="Campaign is inactive.")
    lead = db.get(Lead, body.lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    try:
        enrollment, status = svc.enroll(db, campaign, lead)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"enrollment": _enrollment_public(enrollment, lead), "outcome": status}


@router.get("/enrollments")
def list_enrollments(
    campaign_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    stmt = select(NurtureEnrollment).where(NurtureEnrollment.user_id == user.id)
    if campaign_id is not None:
        stmt = stmt.where(NurtureEnrollment.campaign_id == campaign_id)
    rows = db.scalars(stmt.order_by(NurtureEnrollment.enrolled_at.desc()).limit(200)).all()
    leads = {l.id: l for l in db.scalars(select(Lead).where(Lead.user_id == user.id)).all()}
    return {"enrollments": [_enrollment_public(r, leads.get(r.lead_id)) for r in rows]}


@router.post("/enrollments/{enrollment_id}/stop")
def stop_enrollment(
    enrollment_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    enrollment = _get_owned_enrollment(db, enrollment_id, user)
    svc.stop(db, enrollment)
    db.commit()
    lead = db.get(Lead, enrollment.lead_id)
    return {"enrollment": _enrollment_public(enrollment, lead)}


# --- due-step processing + metrics ---------------------------------------------

@router.post("/process-due")
def process_due(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    surfaced = svc.process_due(db, user_id=user.id)
    return {"steps_surfaced": surfaced}


@router.get("/suppressions")
def list_suppressions(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(NurtureSuppression).where(NurtureSuppression.user_id == user.id).order_by(NurtureSuppression.created_at.desc())
    ).all()
    return {
        "suppressions": [
            {"id": r.id, "value": r.value, "reason": r.reason,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]
    }


@router.post("/suppressions", status_code=201)
def add_suppression(body: SuppressionBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    value = body.value.strip().lower().replace(" ", "")
    if not value:
        raise HTTPException(status_code=422, detail="value is required")
    existing = db.scalar(select(NurtureSuppression).where(NurtureSuppression.user_id == user.id, NurtureSuppression.value == value))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contact is already suppressed.")
    row = NurtureSuppression(user_id=user.id, value=value, reason=body.reason.strip())
    db.add(row)
    db.commit()
    return {"suppression": {"id": row.id, "value": row.value, "reason": row.reason}}


@router.delete("/suppressions/{suppression_id}", status_code=204)
def remove_suppression(suppression_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    row = db.get(NurtureSuppression, suppression_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Suppression not found.")
    db.delete(row)
    db.commit()
