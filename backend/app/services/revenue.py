"""Revenue & ROI tracking (P5 #3) - manual, honest, zero-cost.

Rules:
- Revenue comes only from what the owner/team typed on a **won** deal. A lead
  with no outcome is unknown, never zero revenue.
- Currencies are never converted; every total is grouped per currency.
- Campaign spend is the existing owner-entered ledger (all-time, no dates), so
  ROI is labelled as all-time spend against windowed revenue.
- ROI / cost-per-won are `null` until spend exists in the same currency.
- Win rate is `null` below 10 closed deals in the window ("too early").
"""
import datetime
import math
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CampaignSpend, DealOutcome, Lead, LeadActivity

STATUSES = ("open", "won", "lost")
CURRENCY_RE = re.compile(r"^[A-Z]{2,10}$")
MAX_AMOUNT = 1_000_000_000_000
RATE_MIN_CLOSED = 10


class RevenueError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _today(now: datetime.datetime | None = None) -> datetime.date:
    value = now or datetime.datetime.now(datetime.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc).date()


def _clean(body: dict, today: datetime.date) -> dict:
    status = str(body.get("status") or "open").strip().lower()
    if status not in STATUSES:
        raise RevenueError(f"status must be one of: {', '.join(STATUSES)}")

    try:
        amount = float(body.get("amount") or 0)
    except (TypeError, ValueError):
        raise RevenueError("amount must be a number.")
    if not math.isfinite(amount) or amount < 0 or amount > MAX_AMOUNT:
        raise RevenueError("amount must be a finite number between 0 and 1e12.")

    currency = str(body.get("currency") or "PKR").strip().upper()
    if not CURRENCY_RE.fullmatch(currency):
        raise RevenueError("currency must be 2-10 letters (e.g. PKR, USD).")

    closed_at = body.get("closed_at")
    if isinstance(closed_at, str) and closed_at.strip():
        try:
            closed_at = datetime.date.fromisoformat(closed_at.strip())
        except ValueError:
            raise RevenueError("closed_at must be YYYY-MM-DD.")
    elif closed_at in (None, ""):
        closed_at = None

    if status == "open":
        closed_at = None
    else:
        closed_at = closed_at or today
        if closed_at > today:
            raise RevenueError("closed_at cannot be in the future.")

    note = str(body.get("note") or "").strip()[:500]
    return {"status": status, "amount": amount, "currency": currency, "closed_at": closed_at, "note": note}


def public(row: DealOutcome | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "status": row.status,
        "amount": row.amount,
        "currency": row.currency,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_outcome(db: Session, user_id: int, lead_id: int) -> DealOutcome | None:
    return db.scalar(
        select(DealOutcome).where(DealOutcome.user_id == user_id, DealOutcome.lead_id == lead_id)
    )


def set_outcome(
    db: Session,
    user_id: int,
    lead: Lead,
    body: dict,
    now: datetime.datetime | None = None,
) -> tuple[DealOutcome, bool]:
    values = _clean(body, _today(now))
    row = get_outcome(db, user_id, lead.id)
    created = row is None
    if row is None:
        row = DealOutcome(user_id=user_id, lead_id=lead.id)
        db.add(row)
    row.status = values["status"]
    row.amount = values["amount"]
    row.currency = values["currency"]
    row.closed_at = values["closed_at"]
    row.note = values["note"]
    db.flush()
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=user_id,
            kind="deal_outcome",
            detail=f"Deal {row.status}: {row.currency} {row.amount:g}"
            + (f" (closed {row.closed_at.isoformat()})" if row.closed_at else ""),
        )
    )
    return row, created


def clear_outcome(db: Session, user_id: int, lead: Lead) -> bool:
    row = get_outcome(db, user_id, lead.id)
    if row is None:
        return False
    db.delete(row)
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=user_id,
            kind="deal_outcome_cleared",
            detail="Deal outcome removed - revenue is unknown again.",
        )
    )
    return True


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def revenue_report(db: Session, user_id: int, days: int, now: datetime.datetime | None = None) -> dict:
    days = max(1, min(int(days), 3650))
    today = _today(now)
    cutoff = today - datetime.timedelta(days=days)

    rows = db.scalars(select(DealOutcome).where(DealOutcome.user_id == user_id)).all()
    open_rows = [r for r in rows if r.status == "open"]
    closed = [
        r for r in rows if r.status in ("won", "lost") and r.closed_at and r.closed_at >= cutoff
    ]
    won = [r for r in closed if r.status == "won"]
    lost = [r for r in closed if r.status == "lost"]

    leads_total = int(
        db.scalar(select(func.count()).select_from(Lead).where(Lead.user_id == user_id)) or 0
    )
    leads_with_outcome = int(
        db.scalar(
            select(func.count(func.distinct(DealOutcome.lead_id))).where(
                DealOutcome.user_id == user_id
            )
        )
        or 0
    )

    campaigns_map = {
        lead_id: (campaign or "").strip()
        for lead_id, campaign in db.execute(
            select(Lead.id, Lead.campaign).where(Lead.user_id == user_id)
        ).all()
    }

    spend_rows = db.scalars(select(CampaignSpend).where(CampaignSpend.user_id == user_id)).all()
    spend_by_currency: dict[str, float] = {}
    spend_by_campaign: dict[tuple[str, str], float] = {}
    for row in spend_rows:
        currency = (row.currency or "PKR").strip().upper()
        spend_by_currency[currency] = spend_by_currency.get(currency, 0.0) + float(row.spend or 0)
        key = ((row.campaign or "").strip(), currency)
        spend_by_campaign[key] = spend_by_campaign.get(key, 0.0) + float(row.spend or 0)

    per_currency: dict[str, dict] = {}

    def bucket(currency: str) -> dict:
        return per_currency.setdefault(
            currency,
            {"revenue": 0.0, "won_deals": 0, "lost_deals": 0, "lost_value": 0.0,
             "open_deals": 0, "open_value": 0.0},
        )

    for row in won:
        data = bucket(row.currency)
        data["revenue"] += float(row.amount or 0)
        data["won_deals"] += 1
    for row in lost:
        data = bucket(row.currency)
        data["lost_deals"] += 1
        data["lost_value"] += float(row.amount or 0)
    for row in open_rows:
        data = bucket(row.currency)
        data["open_deals"] += 1
        data["open_value"] += float(row.amount or 0)

    totals: list[dict] = []
    for currency in sorted(set(per_currency) | set(spend_by_currency)):
        data = bucket(currency)
        spend = float(spend_by_currency.get(currency, 0.0) or 0)
        revenue = float(data["revenue"])
        # ROI needs both spend and at least one confirmed won deal: zero won
        # deals means revenue is unknown, not literally zero, so no ROI number.
        roi = (
            round((revenue - spend) / spend * 100, 1)
            if spend > 0 and data["won_deals"]
            else None
        )
        cost_per_won = round(spend / data["won_deals"], 2) if spend > 0 and data["won_deals"] else None
        totals.append(
            {
                "currency": currency,
                "revenue": _money(revenue),
                "won_deals": data["won_deals"],
                "avg_deal": _money(revenue / data["won_deals"]) if data["won_deals"] else None,
                "lost_deals": data["lost_deals"],
                "lost_value": _money(data["lost_value"]),
                "open_deals": data["open_deals"],
                "open_value": _money(data["open_value"]),
                "spend": _money(spend),
                "roi_pct": roi,
                "cost_per_won": cost_per_won,
            }
        )

    campaign_rows: dict[tuple[str, str], dict] = {}
    for row in won:
        campaign = campaigns_map.get(row.lead_id) or "(unattributed)"
        key = (campaign, row.currency)
        data = campaign_rows.setdefault(
            key, {"campaign": campaign, "currency": row.currency, "won_deals": 0, "revenue": 0.0}
        )
        data["won_deals"] += 1
        data["revenue"] += float(row.amount or 0)

    for (campaign, currency), spend in spend_by_campaign.items():
        if campaign and (campaign, currency) not in campaign_rows:
            campaign_rows[(campaign, currency)] = {
                "campaign": campaign,
                "currency": currency,
                "won_deals": 0,
                "revenue": 0.0,
            }

    campaigns: list[dict] = []
    for (campaign, currency), data in campaign_rows.items():
        spend = float(spend_by_campaign.get((campaign, currency), 0.0) or 0)
        revenue = float(data["revenue"])
        campaigns.append(
            {
                "campaign": campaign,
                "currency": currency,
                "won_deals": data["won_deals"],
                "revenue": _money(revenue),
                "spend": _money(spend),
                "roi_pct": round((revenue - spend) / spend * 100, 1)
                if spend > 0 and data["won_deals"]
                else None,
                "cost_per_won": round(spend / data["won_deals"], 2)
                if spend > 0 and data["won_deals"]
                else None,
            }
        )
    campaigns.sort(key=lambda c: (-c["revenue"], -c["spend"], c["campaign"]))

    closed_count = len(closed)
    win_rate = round(len(won) / closed_count * 100, 1) if closed_count >= RATE_MIN_CLOSED else None

    notes = [
        "Revenue is only what you recorded on won deals - a lead with no outcome is unknown, never zero.",
        "Totals are grouped per currency; the platform never converts currencies.",
        f"Revenue counts deals closed in the last {days} days. Campaign spend is all-time owner-entered data (no spend dates), so ROI mixes windows.",
        "ROI and cost-per-won are null until spend exists in the same currency and at least one won deal is recorded; they are not forecasts.",
    ]
    if win_rate is None:
        notes.append(
            f"Win rate stays unknown until {RATE_MIN_CLOSED} closed deals in the window (currently {closed_count})."
        )
    if any(c["campaign"] == "(unattributed)" for c in campaigns):
        notes.append("Won deals without a campaign are grouped as (unattributed) - campaign is never guessed.")

    return {
        "window_days": days,
        "cutoff": cutoff.isoformat(),
        "today": today.isoformat(),
        "outcomes": {
            "won_deals": len(won),
            "lost_deals": len(lost),
            "closed_deals": closed_count,
            "open_deals": len(open_rows),
            "win_rate_pct": win_rate,
            "rates_known": win_rate is not None,
            "rate_gate": RATE_MIN_CLOSED,
        },
        "coverage": {
            "leads_total": leads_total,
            "leads_with_outcome": leads_with_outcome,
            "coverage_pct": round(leads_with_outcome / leads_total * 100, 1) if leads_total else None,
        },
        "totals_by_currency": totals,
        "campaigns": campaigns,
        "notes": notes,
    }
