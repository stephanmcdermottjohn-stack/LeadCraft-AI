"""Webhook infrastructure (P4 #1).

Design rules this module enforces:

- **Store first, interpret second.** Every provider delivery is written to
  `webhook_events` before routing, so a failed Graph call or an unknown page id
  is visible instead of vanishing.
- **Honest routing.** A payload whose page id / phone number id is not
  configured on any workspace is stored as `unrouted` with `user_id = NULL`.
  It is never guessed onto a random tenant.
- **Idempotent.** The provider-scoped event key is UNIQUE, so a Meta retry
  cannot create a second lead or message.
- **Unconfigured means off.** Handlers return 503 while the app secret is
  missing rather than accepting unverified payloads.
"""
import hashlib
import hmac
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import WebhookEvent

# Provider payloads are capped before storage (raw bodies stay out of the DB).
PAYLOAD_CAP = 20000


class WebhookError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def signature_valid(secret: str, raw_body: bytes, header: str | None) -> bool:
    """Verify Meta's `X-Hub-Signature-256: sha256=<hex>` header.

    Comparison is constant-time. A missing secret or header is never "valid" -
    callers must check that a secret is configured before relying on this.
    """
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = header.split("=", 1)[1].strip().lower()
    return hmac.compare_digest(expected, provided)


def store_event(
    db: Session,
    *,
    source: str,
    event_key: str,
    payload: dict,
    signature_valid: bool,
) -> tuple[WebhookEvent, bool]:
    """Insert one delivery, or return the existing row for a retry.

    Returns `(event, created)`. Committing here means the delivery survives
    even if the following processing step throws.
    """
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
    if existing is not None:
        return existing, False

    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    event = WebhookEvent(
        source=source[:30],
        event_key=event_key[:200],
        status="received",
        payload_json=encoded[:PAYLOAD_CAP],
        signature_valid=bool(signature_valid),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent delivery of the same event: treat it as a duplicate.
        db.rollback()
        existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
        if existing is None:
            raise
        return existing, False
    db.refresh(event)
    return event, True


def mark(
    db: Session,
    event: WebhookEvent,
    status: str,
    *,
    user_id: int | None = None,
    lead_id: int | None = None,
    error: str = "",
) -> WebhookEvent:
    """Record the processing outcome. Callers commit."""
    event.status = status
    if user_id is not None:
        event.user_id = user_id
    if lead_id is not None:
        event.lead_id = lead_id
    event.error = (error or "")[:500]
    if status in {"processed", "ignored", "unrouted", "pending_credentials", "error"}:
        import datetime

        event.processed_at = datetime.datetime.now(datetime.timezone.utc)
    return event
