"""BANT qualification endpoints (roadmap P0 #3). Lead-scoped and tenant-
checked like every other lead resource: another user's lead → 404.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Lead, LeadQualification, User
from app.services import qualification as svc

router = APIRouter(prefix="/api/leads")


class QualificationPatch(BaseModel):
    """Manual corrections. Any subset of the 4 dimensions; empty string resets
    that dimension to 'unknown' (unknown is a first-class answer)."""

    budget: str | None = None
    authority: str | None = None
    need: str | None = None
    timing: str | None = None

    def model_post_init(self, __context) -> None:
        for d in svc.DIMENSIONS:
            value = getattr(self, d)
            if value is not None and len(value) > 500:
                raise ValueError(f"{d} must be at most 500 characters")


def _get_owned_lead(db: Session, lead_id: int, user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


def _get_or_create_row(db: Session, lead: Lead) -> LeadQualification:
    row = db.scalar(
        select(LeadQualification).where(LeadQualification.lead_id == lead.id)
    )
    if row is None:
        row = LeadQualification(lead_id=lead.id, user_id=lead.user_id)
        db.add(row)
        db.flush()
    return row


@router.get("/{lead_id}/qualification")
def get_qualification(
    lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    lead = _get_owned_lead(db, lead_id, user)
    row = db.scalar(select(LeadQualification).where(LeadQualification.lead_id == lead.id))
    return {"qualification": svc.serialize(row) if row else svc.empty_public()}


@router.patch("/{lead_id}/qualification")
def patch_qualification(
    lead_id: int,
    body: QualificationPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lead = _get_owned_lead(db, lead_id, user)
    updates = {d: getattr(body, d) for d in svc.DIMENSIONS if getattr(body, d) is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update - send at least one dimension.")
    row = _get_or_create_row(db, lead)
    svc.apply_patch(row, updates)
    db.commit()
    return {"qualification": svc.serialize(row)}
