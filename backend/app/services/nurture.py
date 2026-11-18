"""Nurture workflow logic (P1 #2).

Honest scope: no message is ever SENT. A due step surfaces as the lead's
next_action + a timeline activity — the owner executes the touch (call, or a
channel they have consent for). Consent gating: enrollment requires a
recorded consent_timestamp on the lead, and suppressed contacts are never
actively enrolled.

Timing: step i becomes due at enrolled_at + steps[i].day_offset (UTC).
"""
import datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, LeadActivity, NurtureCampaign, NurtureEnrollment, NurtureSuppression

MAX_STEPS = 8
STATUSES = ("active", "completed", "stopped", "suppressed")


class StepError(ValueError):
    pass


def parse_steps(raw) -> list[dict]:
    """Validate + normalize the campaign script. Raises StepError."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except ValueError as exc:
            raise StepError("steps must be valid JSON") from exc
    if not isinstance(raw, list) or not (1 <= len(raw) <= MAX_STEPS):
        raise StepError(f"steps must be a list of 1-{MAX_STEPS} steps")
    steps = []
    for s in raw:
        if not isinstance(s, dict):
            raise StepError("each step must be an object")
        day = s.get("day_offset")
        message = str(s.get("message", "") or "").strip()
        if isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 365:
            raise StepError("each step needs day_offset 0-365")
        if not message or len(message) > 500:
            raise StepError("each step needs a message of 1-500 chars")
        steps.append({"day_offset": day, "message": message})
    return steps


def _utc(dt: datetime.datetime) -> datetime.datetime:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def is_suppressed(db: Session, user_id: int, lead: Lead) -> bool:
    values = {str(lead.phone or "").replace(" ", "").lower(), str(lead.email or "").lower()}
    values.discard("")
    if not values:
        return False
    rows = db.scalars(select(NurtureSuppression.value).where(NurtureSuppression.user_id == user_id)).all()
    return any(v in values for v in rows)


def enroll(db: Session, campaign: NurtureCampaign, lead: Lead) -> tuple[NurtureEnrollment, str]:
    """Create the enrollment. Returns (enrollment, outcome) where outcome is
    'suppressed' when the contact is on the suppression list."""
    existing = db.scalar(
        select(NurtureEnrollment).where(
            NurtureEnrollment.campaign_id == campaign.id, NurtureEnrollment.lead_id == lead.id
        )
    )
    if existing is not None:
        raise ValueError("Lead is already enrolled in this campaign.")
    if not lead.consent_timestamp:
        raise ValueError("Lead has no recorded consent - enrollment refused.")
    steps = parse_steps(campaign.steps_json)
    status = "suppressed" if is_suppressed(db, campaign.user_id, lead) else "active"
    day0 = steps[0]["day_offset"]
    now = datetime.datetime.now(datetime.timezone.utc)
    enrollment = NurtureEnrollment(
        user_id=campaign.user_id, campaign_id=campaign.id, lead_id=lead.id,
        status=status, steps_total=len(steps), current_step=0,
        enrolled_at=now,
        next_step_at=now + datetime.timedelta(days=day0) if status == "active" else None,
    )
    db.add(enrollment)
    db.flush()
    label = "suppressed contact - not enrolled" if status == "suppressed" else f"campaign '{campaign.name}'"
    db.add(
        LeadActivity(
            lead_id=lead.id, user_id=campaign.user_id, kind="nurture",
            detail=f"Nurture: {label}" if status == "suppressed" else f"Nurture: enrolled in {label} ({len(steps)} steps)",
        )
    )
    return enrollment, status


def stop(db: Session, enrollment: NurtureEnrollment) -> None:
    if enrollment.status != "active":
        return
    enrollment.status = "stopped"
    db.add(
        LeadActivity(
            lead_id=enrollment.lead_id, user_id=enrollment.user_id, kind="nurture",
            detail="Nurture: sequence stopped by owner",
        )
    )


def _surface_step(db: Session, enrollment: NurtureEnrollment, campaign: NurtureCampaign, step_index: int, step: dict) -> None:
    lead = db.get(Lead, enrollment.lead_id)
    total = enrollment.steps_total
    now = datetime.datetime.now(datetime.timezone.utc)
    if lead is not None:
        lead.next_action = step["message"]
        lead.next_action_at = now
    db.add(
        LeadActivity(
            lead_id=enrollment.lead_id, user_id=enrollment.user_id, kind="nurture",
            detail=f"Nurture: touch {step_index + 1}/{total} due - {step['message']}",
        )
    )


def process_due(db: Session, user_id: int | None = None) -> int:
    """Advance every active enrollment whose next step is due. Returns the
    number of steps surfaced. Completes enrollments that run out of steps."""
    stmt = (
        select(NurtureEnrollment)
        .where(NurtureEnrollment.status == "active", NurtureEnrollment.next_step_at.is_not(None))
    )
    if user_id is not None:
        stmt = stmt.where(NurtureEnrollment.user_id == user_id)
    enrollments = db.scalars(stmt).all()
    now = datetime.datetime.now(datetime.timezone.utc)
    surfaced = 0
    for enr in enrollments:
        due = _utc(enr.next_step_at)
        if due > now:
            continue
        campaign = db.get(NurtureCampaign, enr.campaign_id)
        if campaign is None:
            continue
        steps = parse_steps(campaign.steps_json)
        # Surface every step whose time has already passed (catch-up), in
        # order, but only one pass per run keeps behavior predictable.
        while enr.current_step < len(steps):
            step = steps[enr.current_step]
            due_at = _utc(enr.enrolled_at) + datetime.timedelta(days=step["day_offset"])
            if due_at > now:
                break
            _surface_step(db, enr, campaign, enr.current_step, step)
            surfaced += 1
            enr.current_step += 1
            nxt = steps[enr.current_step] if enr.current_step < len(steps) else None
            if nxt is None:
                enr.status = "completed"
                enr.completed_at = now
                enr.next_step_at = None
                lead = db.get(Lead, enr.lead_id)
                if lead is not None:
                    db.add(LeadActivity(
                        lead_id=lead.id, user_id=enr.user_id, kind="nurture",
                        detail=f"Nurture: sequence complete ({len(steps)} steps)",
                    ))
                break
            enr.next_step_at = _utc(enr.enrolled_at) + datetime.timedelta(days=nxt["day_offset"])
    db.commit()
    return surfaced


def metrics(db: Session, campaign: NurtureCampaign) -> dict:
    rows = db.scalars(select(NurtureEnrollment).where(NurtureEnrollment.campaign_id == campaign.id)).all()
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    steps_due_surfaced = sum(
        r.current_step for r in rows if r.status in ("active", "completed")
    )
    return {
        "enrolled_total": len(rows),
        "active": counts["active"],
        "completed": counts["completed"],
        "stopped": counts["stopped"],
        "suppressed": counts["suppressed"],
        "touches_surfaced": steps_due_surfaced,
        "note": "Touches are surfaced as next-actions, not auto-sent (no external provider).",
    }
