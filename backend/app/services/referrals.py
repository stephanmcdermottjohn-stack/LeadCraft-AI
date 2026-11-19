"""Link-based referrals (P2 #1).

Flow: the owner generates a random per-lead code and shares
`/l/<slug>?ref=<code>`; the referred person submits the normal consent form and
the new lead is linked to the referrer. Unknown or cross-tenant codes are
ignored silently (the public capture endpoint must not leak whether a code
exists). Capture-time linking only - a new lead cannot create cycles.

Honesty: only link-based referrals are measurable; manual word-of-mouth is
outside the numbers and the report says so.
"""
import datetime
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadScoreHistory

MIN_REFERRALS_FOR_RATES = 10
CONVERTED_STAGES = ("convert", "retain", "reactivate")


def _generate_code(db: Session, user_id: int) -> str:
    for _ in range(8):
        code = "ref" + secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10]
        taken = db.scalar(
            select(Lead.id).where(Lead.user_id == user_id, Lead.referral_code == code)
        )
        if taken is None:
            return code
    raise RuntimeError("Could not allocate a unique referral code.")


def ensure_code(db: Session, lead: Lead) -> str:
    """Return the lead's code, generating + persisting one on first use."""
    if lead.referral_code:
        return lead.referral_code
    lead.referral_code = _generate_code(db, lead.user_id)
    db.flush()
    return lead.referral_code


def resolve_code(db: Session, user_id: int, code: str) -> Lead | None:
    code = (code or "").strip()
    if not code:
        return None
    return db.scalar(
        select(Lead).where(Lead.user_id == user_id, Lead.referral_code == code)
    )


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def report(db: Session, user_id: int, days: int = 365) -> dict:
    days = max(1, min(3650, int(days)))
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

    referred = db.scalars(
        select(Lead).where(
            Lead.user_id == user_id,
            Lead.referred_by_lead_id.is_not(None),
            Lead.created_at >= since,
        )
    ).all()
    referred_ids = [l.id for l in referred]
    scored_ids: set[int] = set()
    if referred_ids:
        scored_ids = set(
            db.scalars(
                select(LeadScoreHistory.lead_id).where(
                    LeadScoreHistory.user_id == user_id,
                    LeadScoreHistory.lead_id.in_(referred_ids),
                )
            ).all()
        )

    def qualified(lead: Lead) -> bool:
        return lead.lifecycle_stage != "capture" or lead.id in scored_ids

    referrer_ids = {l.referred_by_lead_id for l in referred}
    referrers = {
        l.id: l
        for l in db.scalars(
            select(Lead).where(Lead.user_id == user_id, Lead.id.in_(referrer_ids))
        ).all()
    } if referrer_ids else {}

    rows = []
    for ref_id in referrer_ids:
        ref = referrers.get(ref_id)
        items = [l for l in referred if l.referred_by_lead_id == ref_id]
        converted = sum(
            1 for l in items if l.lifecycle_stage in CONVERTED_STAGES or l.status == "converted"
        )
        rows.append(
            {
                "lead_id": ref_id,
                "name": ref.name if ref else "(deleted lead)",
                "code": ref.referral_code if ref else "",
                "referrals": len(items),
                "qualified": sum(1 for l in items if qualified(l)),
                "converted": converted,
            }
        )
    rows.sort(key=lambda r: (-r["referrals"], r["name"]))

    total = len(referred)
    qualified_total = sum(1 for l in referred if qualified(l))
    converted_total = sum(
        1 for l in referred if l.lifecycle_stage in CONVERTED_STAGES or l.status == "converted"
    )
    rates_known = total >= MIN_REFERRALS_FOR_RATES
    for row in rows:
        row["conversion_rate_pct"] = _rate(row["converted"], row["referrals"]) if rates_known else None

    notes = [
        "Only link-based referrals are measured (capture with ?ref=<code>); manual word-of-mouth is not tracked.",
        "The platform never messages anyone: you share the link, the referred person submits the normal consent form.",
        "Unknown or cross-business codes are ignored at capture - the public form never reveals whether a code exists.",
        "Converted = convert/retain/reactivate stage or CRM status converted.",
    ]
    if total == 0:
        notes.append("No referrals in this window - rates are unknown, not 0%.")
    elif not rates_known:
        notes.append(
            f"Only {total} referral(s) in this window - rates below {MIN_REFERRALS_FOR_RATES} referrals are too early to read."
        )

    return {
        "window_days": days,
        "referrals_total": total,
        "qualified_total": qualified_total,
        "converted_total": converted_total,
        "qualified_rate_pct": _rate(qualified_total, total) if rates_known else None,
        "converted_rate_pct": _rate(converted_total, total) if rates_known else None,
        "rates_known": rates_known,
        "referrers": rows,
        "notes": notes,
    }
