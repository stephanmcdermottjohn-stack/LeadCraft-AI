"""Funnel + campaign reports (P1 #5).

Honesty rules baked in:
- "Reached a stage" comes from the append-only `lead_stage_history` (a lead
  counts once per stage it has ever been recorded in). Current stage is shown
  separately as a snapshot. Stage order is NOT enforced by the API, so the
  report says so instead of pretending the funnel is strictly monotonic.
- Rates are `null` (never 0%) when there is no denominator, and stay `null`
  below 10 leads in the window ("too early").
- Missing attribution is reported as "(unattributed)" - never guessed.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadScoreHistory, LeadStageHistory
from app.services.lifecycle import STAGES

MIN_LEADS_FOR_RATES = 10
CONVERTED_STAGES = ("convert", "retain", "reactivate")
UNATTRIBUTED = "(unattributed)"


def _utc(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _breakdown(leads: list[Lead], qualified_ids: set[int], keyfn) -> list[dict]:
    groups: dict[str, list[Lead]] = {}
    for lead in leads:
        groups.setdefault(keyfn(lead) or UNATTRIBUTED, []).append(lead)
    rows = []
    for key, items in groups.items():
        total = len(items)
        qualified = sum(1 for l in items if l.id in qualified_ids)
        converted = sum(1 for l in items if l.lifecycle_stage in CONVERTED_STAGES or l.status == "converted")
        rows.append(
            {
                "key": key,
                "total": total,
                "qualified": qualified,
                "converted": converted,
                "qualified_rate_pct": _rate(qualified, total),
                "converted_rate_pct": _rate(converted, total),
            }
        )
    rows.sort(key=lambda r: (-r["total"], r["key"]))
    return rows


def funnel_report(db: Session, user_id: int, days: int = 30) -> dict:
    days = max(1, min(365, int(days)))
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(days=days)

    leads = db.scalars(
        select(Lead).where(Lead.user_id == user_id, Lead.created_at >= since)
    ).all()
    lead_ids = [l.id for l in leads]

    history = []
    scored_ids: set[int] = set()
    if lead_ids:
        history = db.scalars(
            select(LeadStageHistory).where(
                LeadStageHistory.user_id == user_id, LeadStageHistory.lead_id.in_(lead_ids)
            )
        ).all()
        scored_ids = set(
            db.scalars(
                select(LeadScoreHistory.lead_id).where(
                    LeadScoreHistory.user_id == user_id, LeadScoreHistory.lead_id.in_(lead_ids)
                )
            ).all()
        )

    # Ever-reached sets from append-only history; leads with no history rows at
    # all fall back to their current stage (their capture row may pre-date the
    # logging change) - stated in the notes.
    reached: dict[str, set[int]] = {s: set() for s in STAGES}
    for row in history:
        if row.to_stage in reached:
            reached[row.to_stage].add(row.lead_id)
    leads_with_history = {row.lead_id for row in history}
    for lead in leads:
        if lead.id not in leads_with_history and lead.lifecycle_stage in reached:
            reached[lead.lifecycle_stage].add(lead.id)

    current_counts = {s: sum(1 for l in leads if l.lifecycle_stage == s) for s in STAGES}
    total = len(leads)
    qualified_ids = {
        l.id for l in leads if l.lifecycle_stage != "capture" or l.id in scored_ids
    }
    converted_ids = {
        l.id for l in leads if l.lifecycle_stage in CONVERTED_STAGES or l.status == "converted"
    }

    funnel = [
        {
            "stage": stage,
            "reached": len(reached[stage]),
            "current": current_counts[stage],
            "reached_rate_pct": _rate(len(reached[stage]), total),
        }
        for stage in STAGES
    ]

    notes = [
        "Funnel counts use lead_stage_history (ever reached a stage); 'current' is a snapshot. "
        "Stage order is not enforced, so a lead can skip or move back.",
        f"Window: leads created in the last {days} day(s) - older leads are outside this report.",
        "Leads without a campaign or UTM value are grouped as (unattributed); missing data is never estimated.",
        "Qualified = left the capture stage or has a score snapshot. Converted = convert/retain/reactivate stage or CRM status converted.",
    ]
    if total == 0:
        notes.append("No leads in this window - rates are unknown, not 0%.")
    elif total < MIN_LEADS_FOR_RATES:
        notes.append(
            f"Only {total} lead(s) in this window - conversion rates below {MIN_LEADS_FOR_RATES} leads are too early to read."
        )

    rates_known = total >= MIN_LEADS_FOR_RATES
    if not rates_known:
        for row in funnel:
            row["reached_rate_pct"] = None

    sources = _breakdown(leads, qualified_ids, lambda l: l.source)
    campaigns = _breakdown(leads, qualified_ids, lambda l: l.campaign.strip())
    utm_sources = _breakdown(leads, qualified_ids, lambda l: l.utm_source.strip())
    if not rates_known:
        for rows in (sources, campaigns, utm_sources):
            for row in rows:
                row["qualified_rate_pct"] = None
                row["converted_rate_pct"] = None

    return {
        "window_days": days,
        "total_leads": total,
        "qualified_leads": len(qualified_ids),
        "converted_leads": len(converted_ids),
        "qualified_rate_pct": _rate(len(qualified_ids), total) if rates_known else None,
        "converted_rate_pct": _rate(len(converted_ids), total) if rates_known else None,
        "funnel": funnel,
        "sources": sources,
        "campaigns": campaigns,
        "utm_sources": utm_sources,
        "rates_known": rates_known,
        "notes": notes,
    }
