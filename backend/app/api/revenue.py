"""Revenue & ROI tracking (P5 #3) - manual, honest, zero external cost.

Role rules: revenue is business-critical financial data, so reading and writing
deal outcomes is restricted to owner, admin or manager. Agents keep their
operational lead workflow (status, timeline, notes) but cannot record money.
Viewers are already write-blocked globally and are also blocked from reading
the revenue report.

Every route is tenant-scoped (`404` for another workspace's lead). Writes append
an append-only `LeadActivity` row, so the lead timeline stays the source of
truth for who changed what. No audit-log duplication (P5 #2 scope).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Lead, User
from app.services import revenue as svc

leads_router = APIRouter(prefix="/api/leads")
router = APIRouter(prefix="/api/reports")

REVENUE_ROLES = ("owner", "admin", "manager")


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_revenue(user: User) -> None:
    if _role(user) not in REVENUE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Owner, admin or manager role required for revenue tracking.",
        )


def _lead(db: Session, user: User, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return lead


class DealOutcomeBody(BaseModel):
    status: str = Field(default="open", max_length=10)
    amount: float = 0
    currency: str = Field(default="PKR", max_length=10)
    closed_at: str | None = Field(default=None, max_length=10)
    note: str = Field(default="", max_length=500)


@leads_router.get("/{lead_id}/outcome")
def get_outcome(
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_revenue(user)
    lead = _lead(db, user, lead_id)
    row = svc.get_outcome(db, lead.user_id, lead.id)
    return {
        "outcome": svc.public(row),
        "can_edit": True,
        "note": "Revenue is manual: only what you record on a won deal counts.",
    }


@leads_router.put("/{lead_id}/outcome")
def upsert_outcome(
    lead_id: int,
    body: DealOutcomeBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_revenue(user)
    lead = _lead(db, user, lead_id)
    try:
        row, created = svc.set_outcome(db, lead.user_id, lead, body.model_dump())
    except svc.RevenueError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return {
        "outcome": svc.public(row),
        "created": created,
        "note": "Deal outcome saved and added to the lead timeline.",
    }


@leads_router.delete("/{lead_id}/outcome")
def delete_outcome(
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_revenue(user)
    lead = _lead(db, user, lead_id)
    removed = svc.clear_outcome(db, lead.user_id, lead)
    if not removed:
        raise HTTPException(status_code=404, detail="No deal outcome recorded for this lead.")
    db.commit()
    return {
        "removed": True,
        "note": "Deal outcome removed - revenue for this lead is unknown again.",
    }


@router.get("/revenue")
def revenue_report(
    days: int = Query(default=30, ge=1, le=3650),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_revenue(user)
    return svc.revenue_report(db, user.id, days)
