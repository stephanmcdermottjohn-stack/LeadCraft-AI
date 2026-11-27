"""Public (no-auth) routes: landing page config per business slug.

Exposes ONLY business-facing display fields — never personal data, never
credentials, never other clients' rows.
"""
import datetime
import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClientSettings, LandingEvent, LandingPage, LandingVariant, User
from app.services import analytics, booking as booking_svc, business_types
from app.services import pages as pages_svc

router = APIRouter(prefix="/api/public")

CONTROL = "control"


def _active_variants(db: Session, user_id: int) -> list[LandingVariant]:
    return db.scalars(
        select(LandingVariant)
        .where(LandingVariant.user_id == user_id, LandingVariant.is_active)
        .order_by(LandingVariant.id.asc())
    ).all()


def _variant_public(v: LandingVariant) -> dict:
    return {
        "label": v.label,
        "headline": v.headline,
        "subtext": v.subtext,
        "cta_label": v.cta_label,
    }


@router.get("/landing/{slug}")
def landing_config(slug: str, variant: str | None = None, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown business page.")
    user = db.get(User, row.user_id)
    # Phase 3D: the template's extra fields drive the landing form. Shown only
    # when the business enables the toggle; "" type = no extras at all.
    extra_fields = business_types.public_extras(row.business_type or "") if row.show_property_fields else []

    # A/B assignment (P1 #1): explicit ?variant= re-serves that arm (the
    # frontend remembers the visitor's arm in localStorage); otherwise the
    # server picks uniformly among the active arms. No active variants →
    # control, and the variant object is absent.
    assigned = CONTROL
    variant_payload = None
    arms = _active_variants(db, row.user_id)
    if arms:
        if variant and variant != CONTROL:
            chosen = next((a for a in arms if a.label == variant), None)
            if chosen is None:
                raise HTTPException(status_code=404, detail="Unknown variant for this page.")
            assigned, variant_payload = chosen.label, _variant_public(chosen)
        elif variant == CONTROL:
            assigned = CONTROL
        else:
            chosen = random.choice(arms)
            assigned, variant_payload = chosen.label, _variant_public(chosen)

    return {
        "slug": slug,
        "business_name": user.business_name if user else "",
        "niche": row.niche,
        "target_area": row.target_area,
        "show_property_fields": bool(row.show_property_fields),
        "business_type": row.business_type or "",
        "extra_fields": extra_fields,
        # P3 #2 white-label presentation (public display fields only).
        "brand_name": row.brand_name or "",
        "logo_url": row.logo_url or "",
        "primary_color": row.primary_color or "",
        "support_email": row.support_email or "",
        "footer_text": row.footer_text or "",
        "hide_platform_brand": bool(row.hide_platform_brand),
        "ab_variant": assigned,
        "variant": variant_payload,
        # P5 #1: booking widget is shown only when the owner enabled it.
        "booking": booking_svc.landing_booking_config(row),
    }


class BookingBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=320)
    service: str = Field(default="", max_length=100)
    intent_notes: str = Field(default="", max_length=2000)
    starts_at: datetime.datetime
    consent: bool
    # Honeypot: same silent reject as the capture form.
    company: str = Field(default="", max_length=200)


@router.get("/pages/{slug}")
def public_page_config(slug: str, db: Session = Depends(get_db)) -> dict:
    """P7 #1: published custom page (block list) + public branding.

    Drafts return 404 so unpublished work is never exposed. Only display
    fields are returned - never contact data, never credentials.
    """
    page = db.scalar(
        select(LandingPage).where(LandingPage.slug == slug, LandingPage.is_published)
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown page.")
    user = db.get(User, page.user_id)
    row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == page.user_id))
    return {
        "slug": page.slug,
        "title": page.title,
        "blocks": pages_svc.blocks_from_json(page.blocks_json),
        "business": {
            "name": user.business_name if user else "",
            "brand_name": (row.brand_name if row else "") or "",
            "logo_url": (row.logo_url if row else "") or "",
            "primary_color": (row.primary_color if row else "") or "",
            "support_email": (row.support_email if row else "") or "",
            "footer_text": (row.footer_text if row else "") or "",
            "hide_platform_brand": bool(row.hide_platform_brand) if row else False,
            "niche": (row.niche if row else "") or "",
            "target_area": (row.target_area if row else "") or "",
        },
        "capture": {
            "page_slug": page.slug,
            "business_slug": (row.landing_slug if row else "") or "",
            "hint": "Consent is required. The platform never messages the lead automatically.",
        },
        "limits": {
            "no_booking_widget": "Custom pages show the consent form only; booking stays on /l/<slug>.",
            "no_html": "Block text is plain text - markup is never rendered.",
        },
    }


@router.get("/landing/{slug}/slots")
def booking_slots(slug: str, date: str = "", db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown business page.")
    if not row.booking_enabled:
        return {"enabled": False, "date": date, "timezone": row.booking_timezone, "slots": []}
    if not date:
        try:
            tz = booking_svc.timezone_of(row)
            date = datetime.datetime.now(tz).date().isoformat()
        except booking_svc.BookingError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc))
    try:
        slots = booking_svc.slots_for_date(db, row, date)
    except booking_svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return {
        "enabled": True,
        "date": date,
        "timezone": row.booking_timezone,
        "slot_minutes": int(row.booking_slot_minutes or 30),
        "services": booking_svc.parse_services(row.booking_services_json),
        "hint": "Times are shown in the business's timezone. No confirmation message is sent by the platform.",
        "slots": slots,
    }


@router.post("/landing/{slug}/book", status_code=201)
def book_appointment(slug: str, body: BookingBody, db: Session = Depends(get_db)) -> dict:
    if body.company:
        raise HTTPException(status_code=400, detail="Invalid submission.")
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown business page.")
    try:
        appointment, lead, created = booking_svc.create_booking(
            db,
            row,
            starts_at=body.starts_at,
            name=body.name,
            phone=body.phone,
            email=body.email,
            service=body.service,
            intent_notes=body.intent_notes,
            consent=body.consent,
        )
    except booking_svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    tz = booking_svc.timezone_of(row)
    local = appointment.starts_at
    if local.tzinfo is None:
        local = local.replace(tzinfo=datetime.timezone.utc)
    local = local.astimezone(tz)
    return {
        "appointment": {
            "starts_at": appointment.starts_at.isoformat(),
            "ends_at": appointment.ends_at.isoformat(),
            "label": local.strftime("%A, %d %b · %I:%M %p").replace(" 0", " "),
            "service": appointment.service,
            "status": appointment.status,
        },
        "lead_created": created,
        "message": "Appointment requested. The business will contact you to confirm - "
        "the platform does not send confirmation or reminder messages.",
    }


@router.post("/landing/{slug}/impression", status_code=204)
def log_impression(slug: str, body: dict | None = None, db: Session = Depends(get_db)) -> None:
    """First-party impression counter: no cookies, no PII, no read access.
    Unknown slugs are counted as nothing (404 would leak slug existence —
    the config endpoint already does that publicly anyway, but here we keep
    it silent and cheap)."""
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None:
        return
    variant = CONTROL
    if isinstance(body, dict):
        candidate = str(body.get("variant", "") or "")
        if candidate == CONTROL or any(a.label == candidate for a in _active_variants(db, row.user_id)):
            variant = candidate
    db.add(LandingEvent(user_id=row.user_id, slug=slug, variant=variant, event="impression"))
    db.commit()


@router.post("/landing/{slug}/events", status_code=204)
def log_analytics_event(slug: str, body: dict | None = None, db: Session = Depends(get_db)) -> None:
    """First-party analytics events (P1 #4): page_view / form_start / submit.

    Cookie-free and PII-free. Malformed payloads and unknown slugs are silently
    ignored (204) so the endpoint cannot be used to probe slug existence and
    never breaks the landing page.
    """
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None or not isinstance(body, dict):
        return
    if analytics.record_event(db, row.user_id, slug, body):
        db.commit()
