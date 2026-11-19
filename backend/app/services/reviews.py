"""Review requests (P2 #1) - consent-first, owner-executed, no fake proof.

Rules:
- Lead must have recorded consent AND must have converted (stage
  convert/retain/reactivate or CRM status converted) - no review asks to
  prospects.
- The platform never sends anything. 'requested' is a log of the owner's own
  ask; 'completed' / 'declined' are logged manually.
- No rating/review text is stored or displayed.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, ReviewRequest

CHANNELS = ("whatsapp", "phone", "email", "in_person")
RESOLVED = ("completed", "declined")
CONVERTED_STAGES = ("convert", "retain", "reactivate")


def is_converted(lead: Lead) -> bool:
    return lead.lifecycle_stage in CONVERTED_STAGES or lead.status == "converted"


def create_request(db: Session, user_id: int, lead: Lead, channel: str, note: str) -> ReviewRequest:
    channel = (channel or "").strip()
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(CHANNELS)}")
    if not lead.consent_timestamp:
        raise ValueError("Lead has no recorded consent - review request refused.")
    if not is_converted(lead):
        raise ValueError("Reviews can only be requested from converted leads.")
    active = db.scalar(
        select(ReviewRequest.id).where(
            ReviewRequest.user_id == user_id,
            ReviewRequest.lead_id == lead.id,
            ReviewRequest.status == "requested",
        )
    )
    if active is not None:
        raise ValueError("A review request is already open for this lead.")
    row = ReviewRequest(
        user_id=user_id, lead_id=lead.id, channel=channel,
        status="requested", note=(note or "").strip()[:500],
    )
    db.add(row)
    db.add(
        LeadActivity(
            lead_id=lead.id, user_id=user_id, kind="review",
            detail=f"Review: requested via {channel} (owner sends it themselves)",
        )
    )
    return row


def resolve(db: Session, row: ReviewRequest, status: str, note: str | None = None) -> ReviewRequest:
    if status not in RESOLVED:
        raise ValueError("status must be completed or declined")
    if row.status != "requested":
        raise ValueError("This review request is already resolved.")
    row.status = status
    row.completed_at = datetime.datetime.now(datetime.timezone.utc) if status == "completed" else None
    if note is not None:
        row.note = (note or "").strip()[:500]
    db.add(
        LeadActivity(
            lead_id=row.lead_id, user_id=row.user_id, kind="review",
            detail=f"Review: {status}" + (f" - {row.note}" if row.note else ""),
        )
    )
    return row


def summary(db: Session, user_id: int) -> dict:
    rows = db.scalars(select(ReviewRequest).where(ReviewRequest.user_id == user_id)).all()
    counts = {"requested": 0, "completed": 0, "declined": 0}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    total = len(rows)
    by_channel = {c: sum(1 for r in rows if r.channel == c) for c in CHANNELS}
    return {
        "total": total,
        "requested": counts["requested"],
        "completed": counts["completed"],
        "declined": counts["declined"],
        "completion_rate_pct": round(counts["completed"] / total * 100, 1) if total else None,
        "by_channel": by_channel,
        "sample_note": (
            "No review asks yet - completion rate is unknown, not 0%."
            if total == 0
            else ("Fewer than 10 requests - treat the rate as directional only." if total < 10 else "")
        ),
        "note": "Requested = you asked through your own channel; the platform sends nothing. "
                "No rating or review text is stored.",
    }
