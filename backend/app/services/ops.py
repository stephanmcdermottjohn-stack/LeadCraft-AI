"""Data, audit & ops (P5 #2): workspace export, telemetry retention, usage.

Honest scope:
- Export is a JSON snapshot of the workspace's own business data. High-volume
  anonymous telemetry (`landing_events`, `analytics_events`) is excluded and
  stated in the payload; it can be removed with the retention tool instead.
- Retention only touches anonymous/operational telemetry. Leads, consent
  records, notes, appointments and the audit log are never purged here.
- Usage reports row counts, not storage bytes - no provider is queried.
"""
import datetime
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AnalyticsEvent,
    Appointment,
    BillingEntry,
    CampaignSpend,
    ClientSettings,
    ContentPost,
    Conversation,
    DealOutcome,
    LandingEvent,
    Lead,
    LeadActivity,
    LeadNote,
    LeadQualification,
    LeadScoreHistory,
    LeadStageHistory,
    Message,
    NurtureCampaign,
    NurtureEnrollment,
    NurtureSuppression,
    ReviewRequest,
    User,
    WebhookEvent,
    WorkspaceMember,
)

EXPORT_LIMIT = 5000
RETENTION_MIN_DAYS = 30
RETENTION_MAX_DAYS = 3650


def _value(raw):
    if isinstance(raw, (datetime.datetime, datetime.date)):
        return raw.isoformat()
    return raw


def _columns(model, exclude: tuple[str, ...] = ()) -> list[str]:
    return [c.name for c in model.__table__.columns if c.name not in exclude]


def _dump(
    db: Session,
    model,
    user_id: int,
    exclude: tuple[str, ...] = (),
    user_field: str = "user_id",
) -> tuple[list[dict], bool]:
    cols = _columns(model, exclude)
    rows = db.scalars(
        select(model)
        .where(getattr(model, user_field) == user_id)
        .order_by(model.id.asc())
        .limit(EXPORT_LIMIT + 1)
    ).all()
    truncated = len(rows) > EXPORT_LIMIT
    return ([{c: _value(getattr(r, c)) for c in cols} for r in rows[:EXPORT_LIMIT]], truncated)


def _dump_messages(db: Session, user_id: int) -> tuple[list[dict], bool]:
    stmt = (
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Lead, Conversation.lead_id == Lead.id)
        .where(Lead.user_id == user_id)
        .order_by(Message.id.asc())
        .limit(EXPORT_LIMIT + 1)
    )
    rows = db.scalars(stmt).all()
    truncated = len(rows) > EXPORT_LIMIT
    cols = _columns(Message)
    return ([{c: _value(getattr(r, c)) for c in cols} for r in rows[:EXPORT_LIMIT]], truncated)


def workspace_export(db: Session, user: User) -> dict:
    """Full JSON snapshot of one workspace (owner/admin only at the route)."""
    data: dict[str, list[dict]] = {}
    truncated: list[str] = []

    tables = {
        "leads": (Lead, ()),
        "lead_notes": (LeadNote, ()),
        "lead_stage_history": (LeadStageHistory, ()),
        "lead_activities": (LeadActivity, ()),
        "lead_qualifications": (LeadQualification, ()),
        "lead_score_history": (LeadScoreHistory, ()),
        "appointments": (Appointment, ()),
        "deal_outcomes": (DealOutcome, ()),
        "content_posts": (ContentPost, ()),
        "conversations": (Conversation, ()),
        "review_requests": (ReviewRequest, ()),
        "campaign_spends": (CampaignSpend, ()),
        "nurture_campaigns": (NurtureCampaign, ()),
        "nurture_enrollments": (NurtureEnrollment, ()),
        "nurture_suppressions": (NurtureSuppression, ()),
        "billing_entries": (BillingEntry, ()),
        # Invite tokens are single-use credentials - never export them.
        "team_members": (WorkspaceMember, ("invite_token",)),
        "webhook_events": (WebhookEvent, ()),
    }

    # Conversations/messages have no user_id column: they are scoped by lead.
    for name, (model, exclude) in tables.items():
        if name == "conversations":
            rows, over = _dump_joined(
                db,
                model,
                Conversation.lead_id,
                Lead.id,
                user.id,
            )
            data[name] = rows
        else:
            user_field = "owner_user_id" if name == "team_members" else "user_id"
            rows, over = _dump(db, model, user.id, exclude, user_field)
            data[name] = rows
        if over:
            truncated.append(name)

    data["messages"], over = _dump_messages(db, user.id)
    if over:
        truncated.append("messages")

    settings_row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    settings = (
        {c.name: _value(getattr(settings_row, c.name)) for c in ClientSettings.__table__.columns}
        if settings_row
        else {}
    )

    return {
        "format": "leadcraft-workspace-export",
        "version": 1,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "workspace": {
            "id": user.id,
            "business_name": user.business_name,
            "email": user.email,
            "plan_tier": user.plan_tier,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "settings": settings,
        "counts": {name: len(rows) for name, rows in data.items()},
        "truncated_tables": truncated,
        "row_limit_per_table": EXPORT_LIMIT,
        "excluded": [
            "landing_events (anonymous A/B impressions)",
            "analytics_events (cookie-free page analytics)",
            "users.password_hash (never exported)",
            "team invite tokens (single-use credentials)",
        ],
        "notes": [
            "This is your workspace's own data snapshot - no other workspace is included.",
            "Telemetry is excluded because it is anonymous and high-volume; use retention to remove it.",
            "The JSON is capped per table; truncated_tables lists anything that hit the cap.",
        ],
        "data": data,
    }


def _dump_joined(db: Session, model, fk_column, lead_id_column, user_id: int) -> tuple[list[dict], bool]:
    stmt = (
        select(model)
        .join(Lead, fk_column == lead_id_column)
        .where(Lead.user_id == user_id)
        .order_by(model.id.asc())
        .limit(EXPORT_LIMIT + 1)
    )
    rows = db.scalars(stmt).all()
    truncated = len(rows) > EXPORT_LIMIT
    cols = _columns(model)
    return ([{c: _value(getattr(r, c)) for c in cols} for r in rows[:EXPORT_LIMIT]], truncated)


def _cutoff(days: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def _clamp_days(days: int) -> int:
    return max(RETENTION_MIN_DAYS, min(int(days), RETENTION_MAX_DAYS))


def retention_preview(db: Session, user_id: int, days: int) -> dict:
    days = _clamp_days(days)
    cutoff = _cutoff(days)
    landing = db.scalar(
        select(func.count())
        .select_from(LandingEvent)
        .where(LandingEvent.user_id == user_id, LandingEvent.created_at < cutoff)
    )
    analytics = db.scalar(
        select(func.count())
        .select_from(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.created_at < cutoff)
    )
    webhook = db.scalar(
        select(func.count())
        .select_from(WebhookEvent)
        .where(
            WebhookEvent.user_id == user_id,
            WebhookEvent.received_at < cutoff,
            WebhookEvent.status.in_(("processed", "ignored")),
        )
    )
    return {
        "days": days,
        "cutoff": cutoff.isoformat(),
        "counts": {
            "landing_events": int(landing or 0),
            "analytics_events": int(analytics or 0),
            "webhook_events": int(webhook or 0),
        },
        "total": int(landing or 0) + int(analytics or 0) + int(webhook or 0),
        "kept": [
            "leads and consent timestamps",
            "notes, stage history and lead activities",
            "appointments",
            "the audit log",
            "webhook rows that are not processed/ignored (retryable)",
        ],
        "notes": [
            "Only anonymous/operational telemetry older than the cutoff is removed.",
            "This cannot be undone. Export first if the data matters to you.",
        ],
    }


def retention_purge(db: Session, user_id: int, days: int) -> dict:
    days = _clamp_days(days)
    cutoff = _cutoff(days)
    landing = db.execute(
        delete(LandingEvent).where(LandingEvent.user_id == user_id, LandingEvent.created_at < cutoff)
    ).rowcount
    analytics = db.execute(
        delete(AnalyticsEvent).where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.created_at < cutoff)
    ).rowcount
    webhook = db.execute(
        delete(WebhookEvent).where(
            WebhookEvent.user_id == user_id,
            WebhookEvent.received_at < cutoff,
            WebhookEvent.status.in_(("processed", "ignored")),
        )
    ).rowcount
    return {
        "days": days,
        "cutoff": cutoff.isoformat(),
        "deleted": {
            "landing_events": int(landing or 0),
            "analytics_events": int(analytics or 0),
            "webhook_events": int(webhook or 0),
        },
        "total_deleted": int(landing or 0) + int(analytics or 0) + int(webhook or 0),
        "note": "Telemetry deleted. Leads, notes, appointments and the audit log were not touched.",
    }


def _count(db: Session, model, user_id: int) -> int:
    return int(
        db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) or 0
    )


def _count_joined(db: Session, model, fk_column, lead_id_column, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .join(Lead, fk_column == lead_id_column)
            .where(Lead.user_id == user_id)
        )
        or 0
    )


def usage(db: Session, user: User) -> dict:
    counts = {
        "leads": _count(db, Lead, user.id),
        "appointments": _count(db, Appointment, user.id),
        "deal_outcomes": _count(db, DealOutcome, user.id),
        "content_posts": _count(db, ContentPost, user.id),
        "lead_notes": _count(db, LeadNote, user.id),
        "lead_stage_history": _count(db, LeadStageHistory, user.id),
        "lead_activities": _count(db, LeadActivity, user.id),
        "review_requests": _count(db, ReviewRequest, user.id),
        "nurture_enrollments": _count(db, NurtureEnrollment, user.id),
        "webhook_events": _count(db, WebhookEvent, user.id),
        "landing_events": _count(db, LandingEvent, user.id),
        "analytics_events": _count(db, AnalyticsEvent, user.id),
        "conversations": _count_joined(db, Conversation, Conversation.lead_id, Lead.id, user.id),
        "messages": int(
            db.scalar(
                select(func.count())
                .select_from(Message)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .join(Lead, Conversation.lead_id == Lead.id)
                .where(Lead.user_id == user.id)
            )
            or 0
        ),
        "team_members_active": int(
            db.scalar(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.owner_user_id == user.id, WorkspaceMember.status == "active")
            )
            or 0
        ),
    }
    last_lead = db.scalar(select(func.max(Lead.created_at)).where(Lead.user_id == user.id))
    last_appointment = db.scalar(
        select(func.max(Appointment.created_at)).where(Appointment.user_id == user.id)
    )
    last_webhook = db.scalar(
        select(func.max(WebhookEvent.received_at)).where(WebhookEvent.user_id == user.id)
    )
    return {
        "counts": counts,
        "last": {
            "lead_at": last_lead.isoformat() if last_lead else None,
            "appointment_at": last_appointment.isoformat() if last_appointment else None,
            "webhook_at": last_webhook.isoformat() if last_webhook else None,
        },
        "retention": {
            "min_days": RETENTION_MIN_DAYS,
            "max_days": RETENTION_MAX_DAYS,
            "export_row_limit": EXPORT_LIMIT,
        },
        "notes": [
            "Counts are database rows for this workspace only, not storage bytes.",
            "Anonymous telemetry rows can be removed with the retention tool; business records are never purged there.",
            "There is no external metering provider - these numbers come from your own database.",
        ],
    }
