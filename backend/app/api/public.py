"""Public (no-auth) routes: landing page config per business slug.

Exposes ONLY business-facing display fields — never personal data, never
credentials, never other clients' rows.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClientSettings, User
from app.services import business_types

router = APIRouter(prefix="/api/public")


@router.get("/landing/{slug}")
def landing_config(slug: str, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown business page.")
    user = db.get(User, row.user_id)
    # Phase 3D: the template's extra fields drive the landing form. Shown only
    # when the business enables the toggle; "" type = no extras at all.
    extra_fields = business_types.public_extras(row.business_type or "") if row.show_property_fields else []
    return {
        "slug": slug,
        "business_name": user.business_name if user else "",
        "niche": row.niche,
        "target_area": row.target_area,
        "show_property_fields": bool(row.show_property_fields),
        "business_type": row.business_type or "",
        "extra_fields": extra_fields,
    }
