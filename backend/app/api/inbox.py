"""Unified inbox v1 (P1 #3): conversations + messages over the existing
tables. Tenant-checked everywhere.

Consent-first rule (roadmap Section 0) enforced here: an owner may record an
inbound message anytime (the lead spoke first through a consented channel),
but an OUTBOUND reply is only possible once at least one inbound message
exists in that conversation. No auto-bot in v1: the owner writes replies; the
platform records them (actual WhatsApp delivery needs a provider — deferred
with a cost decision). Channels allowlist keeps the data clean.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Conversation, Lead, Message, User

router = APIRouter(prefix="/api/inbox")

CHANNELS = ("whatsapp_inbound", "website_chat", "direct_message")


def _dt_key(dt: datetime.datetime | None) -> datetime.datetime:
    """Normalize for sorting (SQLite returns naive datetimes, Postgres aware)."""
    if dt is None:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


class ConversationBody(BaseModel):
    lead_id: int
    channel: str = Field(min_length=1, max_length=50)


class MessageBody(BaseModel):
    direction: str = Field(min_length=2, max_length=3)  # in | out
    body: str = Field(min_length=1, max_length=2000)

    def model_post_init(self, __context) -> None:
        self.body = self.body.strip()
        self.direction = self.direction.strip()
        if not self.body:
            raise ValueError("body must not be empty")


def _get_owned_conversation(db: Session, conversation_id: int, user: User) -> Conversation:
    row = db.get(Conversation, conversation_id)
    if row is None or row.lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return row


def _conversation_public(c: Conversation) -> dict:
    lead = c.lead
    ordered = sorted(c.messages, key=lambda m: _dt_key(m.sent_at), reverse=True)
    last = ordered[0] if ordered else None
    has_inbound = any(m.direction == "in" for m in ordered)
    return {
        "id": c.id,
        "lead_id": lead.id,
        "lead_name": lead.name,
        "lead_phone": lead.phone,
        "channel": c.channel,
        "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        "last_message_preview": (last.body[:120] if last else ""),
        "last_direction": (last.direction if last else ""),
        "has_inbound": has_inbound,
    }


def _message_public(m: Message) -> dict:
    return {
        "id": m.id,
        "direction": m.direction,
        "body": m.body,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
    }


@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Conversation)).all()
    own = [c for c in rows if c.lead.user_id == user.id]
    own.sort(key=lambda c: _dt_key(c.last_message_at), reverse=True)
    return {"conversations": [_conversation_public(c) for c in own]}


@router.post("/conversations", status_code=201)
def create_conversation(
    body: ConversationBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    if body.channel not in CHANNELS:
        raise HTTPException(status_code=400, detail=f"channel must be one of: {sorted(CHANNELS)}")
    lead = db.get(Lead, body.lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if not lead.consent_timestamp:
        raise HTTPException(status_code=400, detail="Lead has no recorded consent - no conversation allowed.")
    row = Conversation(lead_id=lead.id, channel=body.channel)
    db.add(row)
    db.commit()
    return {"conversation": _conversation_public(row)}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    row = _get_owned_conversation(db, conversation_id, user)
    messages = sorted(row.messages, key=lambda m: _dt_key(m.sent_at))
    return {
        "conversation": _conversation_public(row),
        "messages": [_message_public(m) for m in messages],
    }


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def post_message(
    conversation_id: int, body: MessageBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    row = _get_owned_conversation(db, conversation_id, user)
    if body.direction not in ("in", "out"):
        raise HTTPException(status_code=400, detail="direction must be 'in' or 'out'")
    if body.direction == "out":
        # Consent-first: never outbound-first. An inbound row must exist.
        has_inbound = any(m.direction == "in" for m in row.messages)
        if not has_inbound:
            raise HTTPException(
                status_code=400,
                detail="Outbound-first contact is not allowed - record the lead's inbound message first.",
            )
    msg = Message(conversation_id=row.id, direction=body.direction, body=body.body)
    db.add(msg)
    row.last_message_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return {"message": _message_public(msg)}
