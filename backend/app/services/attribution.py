"""Advanced attribution (P2 #2) - honest, first-party, no multi-touch fiction.

Available data: one capture-time attribution set per lead (campaign + UTM +
variant + referral) and the append-only stage history. So this report offers
coverage, per-campaign outcomes, owner-entered spend cost ratios, and
time-to-qualify/convert - and explicitly refuses to claim multi-touch
attribution or ROI (no revenue is tracked anywhere).
"""
import datetime
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignSpend, Lead, LeadScoreHistory, LeadStageHistory

MIN_LEADS_FOR_RATES = 10
CONVERTED_STAGES = ("convert", "retain", "reactivate")
UNATTRIBUTED = "(unattributed)"


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _cost(spend: float | None, count: int) -> float | None:
    if spend is None or count <= 0:
        return None
    return round(spend / count, 1)


def _utc(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def upsert_spend(
    db: Session, user_id: int, campaign: str, spend: float, currency: str, notes: str
) -> CampaignSpend:
    campaign = (campaign or "").strip()
    if not campaign:
        raise ValueError("campaign is required")
    if spend is None or spend < 0:
        raise ValueError("spend must be zero or positive")
    row = db.scalar(
        select(CampaignSpend).where(
            CampaignSpend.user_id == user_id, CampaignSpend.campaign == campaign
        )
    )
    if row is None:
        row = CampaignSpend(user_id=user_id, campaign=campaign)
        db.add(row)
    row.spend = float(spend)
    row.currency = (currency or "PKR").strip()[:10] or "PKR"
    row.notes = (notes or "").strip()[:500]
    db.flush()
    return row


def report(db: Session, user_id: int, days: int = 365) -> dict:
    days = max(1, min(3650, int(days)))
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

    qualified_ids = {
        l.id for l in leads if l.lifecycle_stage != "capture" or l.id in scored_ids
    }
    converted_ids = {
        l.id for l in leads if l.lifecycle_stage in CONVERTED_STAGES or l.status == "converted"
    }

    # --- time-to-stage (platform timestamps only) -----------------------------
    first_seen: dict[tuple[int, str], datetime.datetime] = {}
    for row in sorted(history, key=lambda h: _utc(h.changed_at) or now):
        if row.to_stage not in ("qualify", "convert"):
            continue
        key = (row.lead_id, row.to_stage)
        changed = _utc(row.changed_at)
        if changed and key not in first_seen:
            first_seen[key] = changed
    created = {l.id: _utc(l.created_at) for l in leads}

    def _days(stage: str) -> list[float]:
        values = []
        for lead_id in lead_ids:
            seen = first_seen.get((lead_id, stage))
            start = created.get(lead_id)
            if seen and start:
                values.append(max(0.0, (seen - start).total_seconds() / 86400.0))
        return values

    tq = _days("qualify")
    tc = _days("convert")

    # --- campaign rows (leads + owner-entered spend) ---------------------------
    spends = {
        r.campaign: r
        for r in db.scalars(select(CampaignSpend).where(CampaignSpend.user_id == user_id)).all()
    }
    groups: dict[str, list[Lead]] = {}
    for lead in leads:
        groups.setdefault(lead.campaign.strip() or UNATTRIBUTED, []).append(lead)
    # Spend recorded for campaigns with no leads in the window still surfaces.
    for name in spends:
        groups.setdefault(name, [])

    rates_known = len(leads) >= MIN_LEADS_FOR_RATES
    campaigns = []
    for name, items in groups.items():
        total = len(items)
        qualified = sum(1 for l in items if l.id in qualified_ids)
        converted = sum(1 for l in items if l.id in converted_ids)
        spend_row = spends.get(name)
        spend = float(spend_row.spend) if spend_row is not None else None
        campaigns.append(
            {
                "campaign": name,
                "leads": total,
                "qualified": qualified,
                "converted": converted,
                "qualified_rate_pct": _rate(qualified, total) if rates_known else None,
                "converted_rate_pct": _rate(converted, total) if rates_known else None,
                "spend": spend,
                "currency": spend_row.currency if spend_row is not None else "",
                "cost_per_lead": _cost(spend, total),
                "cost_per_qualified": _cost(spend, qualified),
                "cost_per_conversion": _cost(spend, converted),
            }
        )
    campaigns.sort(key=lambda r: (-r["leads"], r["campaign"]))

    utm_groups: dict[str, list[Lead]] = {}
    for lead in leads:
        utm_groups.setdefault(lead.utm_source.strip() or UNATTRIBUTED, []).append(lead)
    utm_sources = [
        {
            "utm_source": name,
            "leads": len(items),
            "qualified": sum(1 for l in items if l.id in qualified_ids),
            "converted": sum(1 for l in items if l.id in converted_ids),
        }
        for name, items in utm_groups.items()
    ]
    utm_sources.sort(key=lambda r: (-r["leads"], r["utm_source"]))

    total = len(leads)
    tagged_campaign = sum(1 for l in leads if l.campaign.strip())
    tagged_utm = sum(1 for l in leads if l.utm_source.strip())
    tagged_any = sum(1 for l in leads if l.campaign.strip() or l.utm_source.strip())
    coverage = {
        "leads": total,
        "campaign_tagged": tagged_campaign,
        "utm_tagged": tagged_utm,
        "any_tagged": tagged_any,
        "campaign_coverage_pct": _rate(tagged_campaign, total),
        "utm_coverage_pct": _rate(tagged_utm, total),
        "any_coverage_pct": _rate(tagged_any, total),
    }

    notes = [
        "Attribution is capture-time only (one campaign/UTM set per lead) - no multi-touch modelling.",
        "Spend is owner-entered per campaign; costs stay unknown until it is set. Revenue is not tracked, so ROI is not computed.",
        "Missing campaign/UTM tags are reported as coverage gaps, never inferred.",
        "Time-to-stage uses platform timestamps (lead created_at -> first stage-history row); it is not backdated or estimated.",
    ]
    if total == 0:
        notes.append("No leads in this window - coverage and rates are unknown, not 0%.")
    elif not rates_known:
        notes.append(
            f"Only {total} lead(s) in this window - rates below {MIN_LEADS_FOR_RATES} leads are too early to read."
        )
    if not tq:
        notes.append("No lead has a qualify stage change yet - median time-to-qualify is unknown.")
    if not tc:
        notes.append("No lead has a convert stage change yet - median time-to-convert is unknown.")

    return {
        "window_days": days,
        "coverage": coverage,
        "median_time_to_qualify_days": round(statistics.median(tq), 1) if tq else None,
        "median_time_to_convert_days": round(statistics.median(tc), 1) if tc else None,
        "time_to_qualify_samples": len(tq),
        "time_to_convert_samples": len(tc),
        "campaigns": campaigns,
        "utm_sources": utm_sources,
        "rates_known": rates_known,
        "notes": notes,
    }
