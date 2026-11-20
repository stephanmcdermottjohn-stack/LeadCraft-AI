"""Public (no-auth) routes: landing page config per business slug.

Exposes ONLY business-facing display fields — never personal data, never
credentials, never other clients' rows.
"""
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClientSettings, LandingEvent, LandingVariant, User
from app.services import analytics, business_types

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
