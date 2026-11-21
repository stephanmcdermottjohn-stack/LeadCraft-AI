"""Integration operations (P4 #3): workspace-scoped webhook event log + retry.

Read access is owner/admin only because stored payloads contain lead contact
details. Unrouted deliveries (`user_id IS NULL`) belong to no workspace and are
visible only to platform admins - never to a random tenant.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import User, WebhookEvent
from app.services import meta_leadgen, webhooks, whatsapp

router = APIRouter(prefix="/api/integrations")

OPS_ROLES = ("owner", "admin")
RETRYABLE = {"unrouted", "pending_credentials", "error", "received"}


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_ops(user: User) -> None:
    if _role(user) not in OPS_ROLES:
        raise HTTPException(status_code=403, detail="Owner or admin role required for integrations.")


def _public(event: WebhookEvent, *, include_payload: bool = False) -> dict:
    data = {
        "id": event.id,
        "source": event.source,
        "event_key": event.event_key,
        "status": event.status,
        "signature_valid": bool(event.signature_valid),
        "lead_id": event.lead_id,
        "error": event.error,
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
    }
    if include_payload:
        data["payload"] = event.payload_json
    return data


@router.get("/events")
def list_events(
    source: str = "",
    status: str = "",
    limit: int = 50,
    include_unrouted: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_ops(user)
    limit = max(1, min(limit, 200))
    stmt = select(WebhookEvent).where(WebhookEvent.user_id == user.id)
    if include_unrouted:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Only a platform admin can list unrouted deliveries.")
        stmt = select(WebhookEvent).where(
            (WebhookEvent.user_id == user.id) | (WebhookEvent.user_id.is_(None))
        )
    if source:
        if source not in ("meta_leadgen", "whatsapp"):
            raise HTTPException(status_code=400, detail="source must be meta_leadgen or whatsapp.")
        stmt = stmt.where(WebhookEvent.source == source)
    if status:
        stmt = stmt.where(WebhookEvent.status == status)
    rows = db.scalars(stmt.order_by(WebhookEvent.id.desc()).limit(limit)).all()
    return {
        "events": [_public(e) for e in rows],
        "count": len(rows),
        "retryable_statuses": sorted(RETRYABLE),
    }


@router.get("/events/{event_id}")
def get_event(
    event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _require_ops(user)
    event = db.get(WebhookEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook event not found.")
    return {"event": _public(event, include_payload=True)}


@router.post("/events/{event_id}/retry")
def retry_event(
    event_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Re-run routing/processing for a stored delivery.

    Useful after adding the Page access token or the page/phone number id.
    Nothing is re-fetched from Meta unless the event is a leadgen delivery and
    a Page access token is configured.
    """
    _require_ops(user)
    event = db.get(WebhookEvent, event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook event not found.")
    if event.status not in RETRYABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Event status '{event.status}' is not retryable (retryable: {sorted(RETRYABLE)}).",
        )
    config = get_settings()
    if event.source == "meta_leadgen":
        meta_leadgen.process_event(db, event, config)
    elif event.source == "whatsapp":
        whatsapp.process_event(db, event)
    else:
        raise HTTPException(status_code=400, detail="Unknown event source.")
    db.commit()
    db.refresh(event)
    return {
        "event": _public(event),
        "note": "Retry recorded. The event log shows the current outcome; nothing is silently retried again.",
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
