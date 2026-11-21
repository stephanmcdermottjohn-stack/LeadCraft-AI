"""WhatsApp Cloud API inbound processing (P4 #2).

Inbound only. The platform records what the contact sent; **no auto-reply is
ever sent** (that would be outbound-first and needs the Cloud API send path,
which stays deferred). A message from an unknown number creates a consented
lead (`source='whatsapp_inbound'`, inbound time as the consent timestamp) plus
a conversation, so the owner can answer manually from the inbox.

Routing is per workspace via `ClientSettings.whatsapp_phone_number_id`. An
unknown phone number id becomes an `unrouted` event - never a guessed tenant.
"""
import datetime
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientSettings, Conversation, Lead, LeadStageHistory, Message, WebhookEvent
from app.services import webhooks

SUPPORTED_TEXT_TYPES = {"text", "button", "interactive"}


def normalize_phone(value: str) -> str:
    """Digits only, so `+92 300...`, `92300...` compare equal."""
    return re.sub(r"\D", "", value or "")


def parse_messages(payload: dict) -> list[dict]:
    """Flatten a WhatsApp webhook body into one dict per inbound message."""
    out: list[dict] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = str(metadata.get("phone_number_id") or "")
            contacts = {
                normalize_phone(str(c.get("wa_id") or "")): str(
                    (c.get("profile") or {}).get("name") or ""
                )
                for c in value.get("contacts") or []
                if isinstance(c, dict)
            }
            for message in value.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                message_id = str(message.get("id") or "").strip()
                sender = str(message.get("from") or "").strip()
                if not message_id or not sender:
                    continue
                msg_type = str(message.get("type") or "unknown")
                out.append(
                    {
                        "message_id": message_id,
                        "from": sender,
                        "contact_name": contacts.get(normalize_phone(sender), ""),
                        "phone_number_id": phone_number_id,
                        "type": msg_type,
                        "text": extract_text(message, msg_type),
                        # Kept as the provider's epoch string: the consent
                        # timestamp must be the message time, not processing time.
                        "timestamp": str(message.get("timestamp") or ""),
                    }
                )
    return out


def extract_text(message: dict, msg_type: str) -> str:
    """Store the human text; media is labelled, never downloaded."""
    if msg_type == "text":
        return str((message.get("text") or {}).get("body") or "").strip()
    if msg_type == "button":
        return str((message.get("button") or {}).get("text") or "").strip()
    if msg_type == "interactive":
        interactive = message.get("interactive") or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return str(reply.get("title") or "").strip()
    caption = ""
    for kind in ("image", "video", "document"):
        block = message.get(kind)
        if isinstance(block, dict):
            caption = str(block.get("caption") or "").strip()
            break
    label = f"[{msg_type} received - media not downloaded]"
    return f"{caption}\n{label}".strip() if caption else label


def _timestamp(raw) -> datetime.datetime:
    try:
        return datetime.datetime.fromtimestamp(int(raw), tz=datetime.timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.datetime.now(datetime.timezone.utc)


def event_key(message: dict) -> str:
    return f"whatsapp:{message['message_id']}"[:200]


def _find_workspace(db: Session, phone_number_id: str) -> ClientSettings | None:
    if not phone_number_id:
        return None
    return db.scalar(
        select(ClientSettings).where(ClientSettings.whatsapp_phone_number_id == phone_number_id)
    )


def _find_lead_by_phone(db: Session, user_id: int, phone: str) -> Lead | None:
    target = normalize_phone(phone)
    if not target:
        return None
    # Phone formats differ per source; compare digit-normalized values. Bounded
    # to this workspace's leads, which is the only data in scope.
    rows = db.scalars(select(Lead).where(Lead.user_id == user_id).order_by(Lead.id.desc())).all()
    for row in rows:
        if normalize_phone(row.phone) == target:
            return row
    return None


def process_event(db: Session, event: WebhookEvent) -> WebhookEvent:
    """Route one inbound message into lead + conversation + message. Caller commits."""
    try:
        data = json.loads(event.payload_json or "{}")
    except ValueError:
        return webhooks.mark(db, event, "error", error="Stored payload is not valid JSON.")

    phone_number_id = str(data.get("phone_number_id") or "")
    settings_row = _find_workspace(db, phone_number_id)
    if settings_row is None:
        return webhooks.mark(
            db,
            event,
            "unrouted",
            error=f"No workspace is configured for WhatsApp phone number id '{phone_number_id or 'unknown'}'.",
        )
    if event.user_id is None:
        event.user_id = settings_row.user_id

    sent_at = _timestamp(data.get("timestamp"))
    lead = _find_lead_by_phone(db, settings_row.user_id, str(data.get("from") or ""))
    if lead is None:
        lead = Lead(
            user_id=settings_row.user_id,
            source="whatsapp_inbound",
            name=str(data.get("contact_name") or "").strip() or str(data.get("from") or "WhatsApp contact"),
            phone=str(data.get("from") or ""),
            email="",
            area="",
            intent_notes="",
            consent_timestamp=sent_at,
            score=0,
            status="new",
            lifecycle_stage="capture",
            metadata_json=json.dumps(
                {
                    "integration": "whatsapp_cloud",
                    "phone_number_id": phone_number_id,
                    "consent_note": "The contact messaged this business first; inbound time is the consent timestamp.",
                }
            ),
            created_at=sent_at,
        )
        db.add(lead)
        db.flush()
        db.add(
            LeadStageHistory(
                lead_id=lead.id,
                user_id=settings_row.user_id,
                from_stage="",
                to_stage="capture",
                note="captured via WhatsApp inbound message",
            )
        )

    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.lead_id == lead.id, Conversation.channel == "whatsapp_inbound")
        .order_by(Conversation.id.desc())
    )
    if conversation is None:
        conversation = Conversation(lead_id=lead.id, channel="whatsapp_inbound")
        db.add(conversation)
        db.flush()

    body = str(data.get("text") or "").strip() or "[empty message]"
    db.add(
        Message(
            conversation_id=conversation.id,
            direction="in",
            body=body[:2000],
            sent_at=sent_at,
        )
    )
    conversation.last_message_at = sent_at
    db.flush()
    return webhooks.mark(db, event, "processed", lead_id=lead.id)
