"""Attribution report + campaign spend registry (P2 #2). Auth, tenant-scoped."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import CampaignSpend, User
from app.services import attribution as svc

router = APIRouter(prefix="/api")


class SpendBody(BaseModel):
    campaign: str = Field(min_length=1, max_length=200)
    spend: float = Field(ge=0)
    currency: str = Field(default="PKR", max_length=10)
    notes: str = Field(default="", max_length=500)


def _public(row: CampaignSpend) -> dict:
    return {
        "id": row.id,
        "campaign": row.campaign,
        "spend": float(row.spend),
        "currency": row.currency,
        "notes": row.notes,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/attribution/report")
def attribution_report(
    days: int = Query(default=365, ge=1, le=3650),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return svc.report(db, user.id, days=days)


@router.get("/campaign-spend")
def list_spend(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(CampaignSpend)
        .where(CampaignSpend.user_id == user.id)
        .order_by(CampaignSpend.campaign.asc())
    ).all()
    return {"spends": [_public(r) for r in rows]}


@router.put("/campaign-spend")
def upsert_spend(
    body: SpendBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        row = svc.upsert_spend(db, user.id, body.campaign, body.spend, body.currency, body.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return {"spend": _public(row)}


@router.delete("/campaign-spend/{spend_id}", status_code=204)
def delete_spend(
    spend_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    row = db.get(CampaignSpend, spend_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign spend not found.")
    db.delete(row)
    db.commit()
