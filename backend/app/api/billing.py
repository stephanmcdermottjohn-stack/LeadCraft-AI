"""Billing endpoints (P3 #3) - manual ledger, owner/admin only.

No payment processing exists here: rows record what the owner says was paid.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import BillingEntry, User
from app.services import billing as svc

router = APIRouter(prefix="/api/billing")


class EntryBody(BaseModel):
    amount: float
    currency: str = Field(default="PKR", max_length=10)
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    paid_until: datetime.date | None = None
    note: str = Field(default="", max_length=500)


class PlanBody(BaseModel):
    plan_tier: str = Field(min_length=1, max_length=50)


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_billing(user: User) -> None:
    if not svc.can_manage_billing(_role(user)):
        raise HTTPException(status_code=403, detail="Owner or admin role required for billing.")


def _public(row: BillingEntry) -> dict:
    return {
        "id": row.id,
        "amount": float(row.amount),
        "currency": row.currency,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "paid_until": row.paid_until.isoformat() if row.paid_until else None,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
def get_billing(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_billing(user)
    data = svc.summary(db, user.id)
    return {
        "plan_tier": user.plan_tier,
        "entries": [_public(r) for r in data["entries"]],
        "entry_count": data["entry_count"],
        "totals_by_currency": data["totals_by_currency"],
        "latest_paid_until": data["latest_paid_until"],
        "plan_tiers": list(svc.PLAN_TIERS),
        "notes": data["notes"],
    }


@router.post("", status_code=201)
def create_entry(
    body: EntryBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _require_billing(user)
    try:
        row = svc.create_entry(
            db, user.id, body.amount, body.currency,
            body.period_start, body.period_end, body.paid_until, body.note,
        )
    except svc.BillingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return {"entry": _public(row)}


@router.patch("/plan")
def set_plan(
    body: PlanBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _require_billing(user)
    tier = body.plan_tier.strip().lower()
    if tier not in svc.PLAN_TIERS:
        raise HTTPException(
            status_code=400, detail=f"plan_tier must be one of: {', '.join(svc.PLAN_TIERS)}"
        )
    user.plan_tier = tier
    db.commit()
    return {
        "plan_tier": tier,
        "note": "Plan label changed manually. This creates no charge and enforces no limits.",
    }


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    _require_billing(user)
    row = db.get(BillingEntry, entry_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Billing entry not found.")
    db.delete(row)
    db.commit()
