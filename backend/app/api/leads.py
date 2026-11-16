"""Lead capture + lead management routes (Phase 3).

Compliance (roadmap Section 0):
- /api/leads/capture is the ONLY public lead-write endpoint. It accepts leads
  that arrived through a consented channel: a landing page the business
  controls (source='landing_page'). The form must carry an explicit consent
  flag; consent_timestamp is recorded server-side (client clocks are not
  trusted). A honeypot field silently rejects bots.
- There is no endpoint that initiates outbound-first contact.
"""
import datetime
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, Lead, User

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
    # Property-module extras stored in metadata_json (Phase 3B).
    budget: str = Field(default="", max_length=100)
    # Honeypot: humans never fill this; bots do. 400 on non-empty.
    company: str = Field(default="", max_length=200)
    # Explicit consent checkbox on the form. Required.
    consent: bool


class LeadStatusBody(BaseModel):
    status: str


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
        "metadata": lead.metadata_json,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
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
        metadata_json=json.dumps({"budget": body.budget} if body.budget else {}),
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(lead)
    db.commit()
    return {"lead": {"id": lead.id, "status": lead.status}}


@router.get("")
def list_leads(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Lead).where(Lead.user_id == user.id).order_by(Lead.created_at.desc()).limit(200)
    ).all()
    return {"leads": [_public_lead(l) for l in rows]}


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
    lead.status = body.status
    db.commit()
    return {"lead": _public_lead(lead)}
