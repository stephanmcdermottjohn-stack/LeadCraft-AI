"""Manual billing ledger (P3 #3).

Honest scope: the owner/admin types in what was paid. There is **no payment
gateway, no card data and no auto-charging**, and plan limits are not enforced
by this module - `users.plan_tier` is changed explicitly and separately.
Totals are grouped per currency; no exchange-rate conversion is applied.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingEntry

PLAN_TIERS = ("basic", "pro", "agency")
BILLING_ROLES = ("owner", "admin")


class BillingError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def can_manage_billing(role: str) -> bool:
    return role in BILLING_ROLES


def create_entry(
    db: Session,
    user_id: int,
    amount: float,
    currency: str,
    period_start: datetime.date | None,
    period_end: datetime.date | None,
    paid_until: datetime.date | None,
    note: str,
) -> BillingEntry:
    if amount is None or amount <= 0:
        raise BillingError("amount must be greater than zero.")
    if period_start and period_end and period_end < period_start:
        raise BillingError("period_end cannot be before period_start.")
    currency = (currency or "PKR").strip().upper()[:10] or "PKR"
    if len(currency) < 2:
        raise BillingError("currency must be a 2-10 character code (e.g. PKR, USD).")
    row = BillingEntry(
        user_id=user_id,
        amount=float(amount),
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        paid_until=paid_until,
        note=(note or "").strip()[:500],
    )
    db.add(row)
    db.flush()
    return row


def summary(db: Session, user_id: int) -> dict:
    rows = db.scalars(
        select(BillingEntry)
        .where(BillingEntry.user_id == user_id)
        .order_by(BillingEntry.created_at.desc(), BillingEntry.id.desc())
    ).all()
    totals: dict[str, float] = {}
    for row in rows:
        totals[row.currency] = round(totals.get(row.currency, 0.0) + float(row.amount), 2)
    paid_until = max((r.paid_until for r in rows if r.paid_until), default=None)
    return {
        "entries": rows,
        "entry_count": len(rows),
        "totals_by_currency": totals,
        "latest_paid_until": paid_until.isoformat() if paid_until else None,
        "notes": [
            "Manual ledger only - no payment gateway, no card data, no auto-charging.",
            "Totals are grouped per currency; no exchange-rate conversion is applied.",
            "Changing the plan tier does not create a charge and does not enforce limits in this version.",
        ],
    }
