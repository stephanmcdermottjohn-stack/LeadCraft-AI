"""Review request endpoints (P2 #1). Auth, tenant-checked. The platform only
records the owner's own review asks - it never sends messages."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Lead, ReviewRequest, User
from app.services import reviews as svc

router = APIRouter(prefix="/api/reviews")


class ReviewBody(BaseModel):
    lead_id: int
    channel: str = Field(default="whatsapp", max_length=30)
    note: str = Field(default="", max_length=500)


class ReviewUpdateBody(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)


def _public(row: ReviewRequest, lead: Lead | None) -> dict:
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "lead_name": lead.name if lead else "",
        "channel": row.channel,
        "status": row.status,
        "note": row.note,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.get("")
def list_reviews(
    lead_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(ReviewRequest).where(ReviewRequest.user_id == user.id)
    if lead_id is not None:
        stmt = stmt.where(ReviewRequest.lead_id == lead_id)
    rows = db.scalars(stmt.order_by(ReviewRequest.requested_at.desc()).limit(500)).all()
    leads = {
        l.id: l for l in db.scalars(select(Lead).where(Lead.user_id == user.id)).all()
    }
    return {
        "reviews": [_public(r, leads.get(r.lead_id)) for r in rows],
        "summary": svc.summary(db, user.id),
    }


@router.post("", status_code=201)
def create_review(
    body: ReviewBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    lead = db.get(Lead, body.lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    try:
        row = svc.create_request(db, user.id, lead, body.channel, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return {"review": _public(row, lead)}


@router.patch("/{review_id}")
def update_review(
    review_id: int,
    body: ReviewUpdateBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(ReviewRequest, review_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Review request not found.")
    try:
        svc.resolve(db, row, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    lead = db.get(Lead, row.lead_id)
    return {"review": _public(row, lead)}
