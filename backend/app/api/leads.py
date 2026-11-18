"""Lead capture + lead management routes (Phase 3).

Compliance (roadmap Section 0):
- /api/leads/capture is the ONLY public lead-write endpoint. It accepts leads
  that arrived through a consented channel: a landing page the business
  controls (source='landing_page'). The form must carry an explicit consent
  flag; consent_timestamp is recorded server-side (client clocks are not
  trusted). A honeypot field silently rejects bots.
- There is no endpoint that initiates outbound-first contact.
"""
import csv
import datetime
import io
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, Lead, LeadActivity, LeadNote, LeadStageHistory, User
from app.services.business_types import EXTRA_VALUE_MAX, extras_for
from app.services.lifecycle import default_next_action, is_valid_stage

router = APIRouter(prefix="/api/leads")

LEAD_SOURCES = {"landing_page", "meta_lead_ad", "google_lead_form", "whatsapp_inbound", "direct_message"}
LEAD_STATUSES = {"new", "contacted", "converted", "archived"}

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$")


class LeadCaptureBody(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=320)
    area: str = Field(default="", max_length=200)
    intent_notes: str = Field(default="", max_length=2000)
    # Legacy Phase 3B property fields — still accepted so older clients and
    # integrations keep working; the generic `extra` dict covers every
    # business template now.
    deal_type: str = Field(default="", max_length=20)   # buy / rent / sell
    property_type: str = Field(default="", max_length=100)
    budget: str = Field(default="", max_length=100)
    # Generic template extras: {field_key: value}. Keys are validated against
    # the business's enabled template server-side.
    extra: dict[str, str] | None = None
    # Source attribution (roadmap P0). URL params passed through by the
    # landing page; length-capped + plain strings only, never trusted clocks.
    campaign: str = Field(default="", max_length=200)
    utm_source: str = Field(default="", max_length=200)
    utm_medium: str = Field(default="", max_length=200)
    utm_content: str = Field(default="", max_length=200)
    utm_term: str = Field(default="", max_length=200)
    landing_variant: str = Field(default="", max_length=50)
    # Honeypot: humans never fill this; bots do. 400 on non-empty.
    company: str = Field(default="", max_length=200)
    # Explicit consent checkbox on the form. Required.
    consent: bool


class LeadImportRow(BaseModel):
    name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=320)
    area: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)


class LeadImportBody(BaseModel):
    # Manual import of a platform lead export (Meta Lead Ads CSV / Google
    # lead form CSV) while the automated webhook is pending. The leads
    # consented on that platform; the importer attests to it.
    source: str
    consent: bool
    rows: list[LeadImportRow]


class LeadStatusBody(BaseModel):
    status: str


class LeadStageBody(BaseModel):
    """Lifecycle stage change + planning fields (roadmap P0). Omitted fields
    keep their current values; stage is required."""
    stage: str
    note: str = Field(default="", max_length=500)
    next_action: str | None = Field(default=None, max_length=500)
    next_action_at: datetime.datetime | None = None
    assigned_to: str | None = Field(default=None, max_length=200)


class LeadNoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("note body must not be blank")
        return v.strip()


def _metadata(lead: Lead) -> dict:
    try:
        parsed = json.loads(lead.metadata_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def _public_lead(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "source": lead.source,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "area": lead.area,
        "intent_notes": lead.intent_notes,
        "consent_timestamp": lead.consent_timestamp.isoformat() if lead.consent_timestamp else None,
        "score": lead.score,
        "status": lead.status,
        "lifecycle_stage": lead.lifecycle_stage,
        "grade": lead.grade,
        "assigned_to": lead.assigned_to,
        "next_action": lead.next_action,
        "next_action_at": lead.next_action_at.isoformat() if lead.next_action_at else None,
        "campaign": lead.campaign,
        "utm_source": lead.utm_source,
        "utm_medium": lead.utm_medium,
        "utm_content": lead.utm_content,
        "utm_term": lead.utm_term,
        "landing_variant": lead.landing_variant,
        "metadata": _metadata(lead),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }


def _public_note(note: LeadNote) -> dict:
    return {
        "id": note.id,
        "body": note.body,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


@router.post("/capture", status_code=201)
def capture(body: LeadCaptureBody, db: Session = Depends(get_db)) -> dict:
    if body.company:
        # Honeypot filled -> bot. Respond like a validation error, quietly.
        raise HTTPException(status_code=400, detail="Invalid submission.")
    if not body.consent:
        raise HTTPException(status_code=400, detail="Consent is required to submit this form.")
    if not body.phone.strip() and not body.email.strip():
        raise HTTPException(status_code=400, detail="Provide a phone number or an email so the business can reply.")

    settings_row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == body.slug))
    if settings_row is None:
        raise HTTPException(status_code=404, detail="Unknown business page.")

    # Template extras: whitelist keys against the business's enabled template.
    # Legacy top-level property fields map into the same metadata dict.
    allowed_keys = {e["key"] for e in extras_for(settings_row.business_type or "")} if settings_row.show_property_fields else set()
    metadata: dict[str, str] = {}
    for k, v in {
        "deal_type": body.deal_type,
        "property_type": body.property_type,
        "budget": body.budget,
    }.items():
        if v and v.strip():
            metadata[k] = v.strip().lower() if k == "deal_type" else v.strip()
    for k, v in (body.extra or {}).items():
        if settings_row.show_property_fields and k in allowed_keys and str(v).strip():
            metadata[k] = str(v).strip()[:EXTRA_VALUE_MAX]

    lead = Lead(
        user_id=settings_row.user_id,
        source="landing_page",
        name=body.name.strip(),
        phone=body.phone.strip(),
        email=body.email.strip().lower(),
        area=body.area.strip(),
        intent_notes=body.intent_notes.strip(),
        consent_timestamp=datetime.datetime.now(datetime.timezone.utc),
        score=0,
        status="new",
        lifecycle_stage="capture",
        # Attribution: plain strings from the landing URL; empty = unknown.
        campaign=body.campaign.strip(),
        utm_source=body.utm_source.strip(),
        utm_medium=body.utm_medium.strip(),
        utm_content=body.utm_content.strip(),
        utm_term=body.utm_term.strip(),
        landing_variant=body.landing_variant.strip(),
        next_action=default_next_action("capture"),
        metadata_json=json.dumps(metadata),
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(lead)
    db.flush()
    db.add(
        LeadStageHistory(
            lead_id=lead.id,
            user_id=settings_row.user_id,
            from_stage="",
            to_stage="capture",
            note="captured via landing page",
        )
    )
    db.commit()
    return {"lead": {"id": lead.id, "status": lead.status}}


@router.post("/import", status_code=201)
def import_leads(
    body: LeadImportBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Manual platform-export import (Meta Lead Ads / Google lead form CSV).
    # The leads already consented on that platform; the importer attests via
    # the consent flag, and consent_timestamp is stamped server-side.
    if body.source not in {"meta_lead_ad", "google_lead_form"}:
        raise HTTPException(
            status_code=400,
            detail="source must be meta_lead_ad or google_lead_form (platform exports).",
        )
    if not body.consent:
        raise HTTPException(status_code=400, detail="Confirm that the imported leads consented on the source platform.")
    if not body.rows:
        raise HTTPException(status_code=400, detail="No rows to import.")
    if len(body.rows) > 500:
        raise HTTPException(status_code=400, detail="Import at most 500 rows at a time.")

    now = datetime.datetime.now(datetime.timezone.utc)
    created = skipped = 0
    for row in body.rows:
        name = row.name.strip()
        phone = row.phone.strip()
        email = row.email.strip().lower()
        if not name or (not phone and not email):
            # Skip malformed rows instead of failing the whole batch.
            skipped += 1
            continue
        db.add(
            Lead(
                user_id=user.id,
                source=body.source,
                name=name,
                phone=phone,
                email=email,
                area=row.area.strip(),
                intent_notes=row.notes.strip(),
                consent_timestamp=now,
                score=0,
                status="new",
                metadata_json="{}",
                created_at=now,
            )
        )
        created += 1
    db.commit()
    return {"imported": created, "skipped": skipped}


@router.get("")
def list_leads(
    q: str = "",
    status: str = "",
    source: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Lead).where(Lead.user_id == user.id)
    if status:
        if status not in LEAD_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {sorted(LEAD_STATUSES)}")
        stmt = stmt.where(Lead.status == status)
    if source:
        if source not in LEAD_SOURCES:
            raise HTTPException(status_code=400, detail=f"source must be one of: {sorted(LEAD_SOURCES)}")
        stmt = stmt.where(Lead.source == source)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            Lead.name.ilike(like) | Lead.phone.ilike(like) | Lead.email.ilike(like)
            | Lead.area.ilike(like) | Lead.intent_notes.ilike(like)
        )
    rows = db.scalars(stmt.order_by(Lead.created_at.desc()).limit(200)).all()
    return {"leads": [_public_lead(l) for l in rows]}


@router.get("/export.csv")
def export_leads_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    rows = db.scalars(select(Lead).where(Lead.user_id == user.id).order_by(Lead.created_at.desc()).limit(5000)).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "created_at", "source", "status", "name", "phone", "email", "area",
         "deal_type", "property_type", "budget", "intent_notes", "consent_timestamp"]
    )
    for l in rows:
        md = _metadata(l)
        writer.writerow(
            [l.id, l.created_at.isoformat() if l.created_at else "", l.source, l.status, l.name,
             l.phone, l.email, l.area, md.get("deal_type", ""), md.get("property_type", ""),
             md.get("budget", ""), l.intent_notes,
             l.consent_timestamp.isoformat() if l.consent_timestamp else ""]
        )
    buffer.seek(0)
    stamp = datetime.date.today().isoformat()
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="leads-{stamp}.csv"'},
    )


@router.get("/{lead_id}/notes")
def list_notes(
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    rows = db.scalars(
        select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc(), LeadNote.id.desc())
    ).all()
    return {"notes": [_public_note(n) for n in rows]}


@router.post("/{lead_id}/notes", status_code=201)
def add_note(
    lead_id: int,
    body: LeadNoteBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    note = LeadNote(
        lead_id=lead.id,
        user_id=user.id,
        body=body.body,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(note)
    db.commit()
    return {"note": _public_note(note)}


@router.patch("/{lead_id}/status")
def update_status(
    lead_id: int,
    body: LeadStatusBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if body.status not in LEAD_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {sorted(LEAD_STATUSES)}")
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    if lead.status != body.status:
        # Timeline activity (P0 #6): log real changes only.
        db.add(
            LeadActivity(
                lead_id=lead.id, user_id=user.id, kind="status_changed",
                detail=f"CRM status: {lead.status} -> {body.status}",
            )
        )
    lead.status = body.status
    # Lifecycle bridge: a won/converted CRM status advances the lifecycle to
    # the convert stage (logged). Other statuses don't touch the stage —
    # the two concepts stay independent.
    if body.status == "converted" and lead.lifecycle_stage != "convert":
        db.add(
            LeadStageHistory(
                lead_id=lead.id,
                user_id=user.id,
                from_stage=lead.lifecycle_stage,
                to_stage="convert",
                note="auto: status set to converted",
            )
        )
        lead.lifecycle_stage = "convert"
        if not lead.next_action:
            lead.next_action = default_next_action("convert")
    db.commit()
    return {"lead": _public_lead(lead)}


@router.patch("/{lead_id}/stage")
def update_stage(
    lead_id: int,
    body: LeadStageBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not is_valid_stage(body.stage):
        raise HTTPException(status_code=400, detail="stage must be one of: capture, qualify, nurture, convert, retain, reactivate")
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")

    previous = lead.lifecycle_stage
    if body.stage != previous:
        lead.lifecycle_stage = body.stage
        db.add(
            LeadStageHistory(
                lead_id=lead.id,
                user_id=user.id,
                from_stage=previous,
                to_stage=body.stage,
                note=body.note,
            )
        )
        # Suggest (never overwrite an owner-set action) the stage's default.
        if not lead.next_action:
            lead.next_action = default_next_action(body.stage)

    # Optional planning fields: omitted = keep existing.
    if body.next_action is not None:
        lead.next_action = body.next_action.strip()
    if body.assigned_to is not None:
        lead.assigned_to = body.assigned_to.strip()
    if "next_action_at" in body.model_fields_set:
        lead.next_action_at = body.next_action_at

    db.commit()
    return {"lead": _public_lead(lead)}


@router.get("/{lead_id}/stage-history")
def stage_history(
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    rows = db.scalars(
        select(LeadStageHistory)
        .where(LeadStageHistory.lead_id == lead_id)
        .order_by(LeadStageHistory.changed_at.desc(), LeadStageHistory.id.desc())
    ).all()
    return {
        "history": [
            {
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "note": h.note,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
            }
            for h in rows
        ]
    }
