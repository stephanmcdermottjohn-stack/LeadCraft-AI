"""Referral endpoints (P2 #1). Auth, tenant-checked.

`POST /api/leads/{id}/code` lives here so referral rules stay in one place; the
public capture endpoint resolves codes through the same service.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, Lead, User
from app.services import referrals as svc

router = APIRouter(prefix="/api/referrals")


@router.post("/leads/{lead_id}/code")
def lead_code(
    lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    code = svc.ensure_code(db, lead)
    db.commit()
    settings_row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    path = f"/l/{settings_row.landing_slug}?ref={code}" if settings_row and settings_row.landing_slug else None
    return {"lead_id": lead.id, "code": code, "path": path}


@router.get("/report")
def referral_report(
    days: int = Query(default=365, ge=1, le=3650),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return svc.report(db, user.id, days=days)
