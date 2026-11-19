"""Unified per-lead activity timeline (roadmap P0 #6). Merges the dedicated
append-only tables (notes, stage history) with the lightweight activity log
(status changes, BANT edits) into one newest-first stream. Read-only by
design: it fabricates nothing and never rewrites history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Conversation, Lead, LeadActivity, LeadNote, LeadStageHistory, Message, User

router = APIRouter(prefix="/api/leads")


@router.get("/{lead_id}/timeline")
def lead_timeline(
    lead_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    events = []
    for n in db.scalars(select(LeadNote).where(LeadNote.lead_id == lead.id)).all():
        events.append({"type": "note", "text": n.body, "at": n.created_at})
    for h in db.scalars(select(LeadStageHistory).where(LeadStageHistory.lead_id == lead.id)).all():
        text = f"Stage: {h.to_stage}" if not h.from_stage else f"Stage: {h.from_stage} → {h.to_stage}"
        if h.note:
            text = f"{text} · {h.note}"
        events.append({"type": "stage", "text": text, "at": h.changed_at})
    for a in db.scalars(select(LeadActivity).where(LeadActivity.lead_id == lead.id)).all():
        text = a.detail or a.kind
        events.append({"type": a.kind, "text": text, "at": a.created_at})
    # Inbox messages (P1 #3): the lead's conversations thread, both directions.
    for conv in db.scalars(select(Conversation).where(Conversation.lead_id == lead.id)).all():
        for m in db.scalars(select(Message).where(Message.conversation_id == conv.id)).all():
            arrow = "→ them" if m.direction == "out" else "← them"
            events.append({"type": "message", "text": f"[{conv.channel}] {arrow}: {m.body}", "at": m.sent_at})
    events.sort(key=lambda e: e["at"] or e["at"].replace(tzinfo=None), reverse=True)
    return {
        "timeline": [
            {"type": e["type"], "text": e["text"], "at": e["at"].isoformat() if e["at"] else None}
            for e in events
        ]
    }
