"""Client settings routes — the personalization source for content prompts."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, User
from app.services import business_types

router = APIRouter(prefix="/api/settings")

# Public URL slugs: lowercase letters/digits with inner hyphens, 3-100 chars.
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$")
RESERVED_SLUGS = {"api", "admin", "login", "register", "settings", "leads", "public", "l"}


class SettingsBody(BaseModel):
    # None (omitted) = keep existing value; "" = clear it.
    niche: str | None = Field(default=None, max_length=200)
    target_area: str | None = Field(default=None, max_length=200)
    brand_voice: str | None = Field(default=None, max_length=500)
    # Public landing page slug (optional). Omitted/empty on PATCH keeps the
    # existing slug; send "auto" to derive one from the business name.
    landing_slug: str | None = Field(default=None, max_length=100)
    # Phase 3B property module toggle (real-estate extra fields on the form).
    show_property_fields: bool | None = None
    # Phase 3D business template (property / ecommerce / hospitality / ...).
    # "" = general. Must match a template key; 400 otherwise.
    business_type: str | None = Field(default=None, max_length=50)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:100]


def _slug_taken(db: Session, slug: str, exclude_user_id: int) -> bool:
    row = db.scalar(select(ClientSettings).where(ClientSettings.landing_slug == slug))
    return row is not None and row.user_id != exclude_user_id


def _public(s: ClientSettings) -> dict:
    return {
        "niche": s.niche,
        "target_area": s.target_area,
        "brand_voice": s.brand_voice,
        "landing_slug": s.landing_slug,
        "show_property_fields": bool(s.show_property_fields),
        "business_type": s.business_type or "",
    }


@router.get("")
def get_settings_route(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    if row is None:
        row = ClientSettings(user_id=user.id)
        db.add(row)
        db.commit()
    return {"settings": _public(row)}


@router.patch("")
def update_settings(body: SettingsBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    if row is None:
        row = ClientSettings(user_id=user.id)
        db.add(row)
    if body.niche is not None:
        row.niche = body.niche.strip()
    if body.target_area is not None:
        row.target_area = body.target_area.strip()
    if body.brand_voice is not None:
        row.brand_voice = body.brand_voice.strip()

    # landing_slug handling: None/"" keeps the current value; "auto" derives a
    # slug from the business name (with -2, -3 … suffix if taken); an explicit
    # slug is validated and must be globally unique (409 otherwise).
    if body.landing_slug is not None and body.landing_slug.strip():
        requested = body.landing_slug.strip()
        if requested == "auto":
            base = _slugify(user.business_name or "business") or "business"
            candidate = base
            n = 2
            while _slug_taken(db, candidate, user.id) or candidate in RESERVED_SLUGS:
                candidate = f"{base}-{n}"
                n += 1
            row.landing_slug = candidate
        else:
            if not SLUG_RE.fullmatch(requested) or requested in RESERVED_SLUGS:
                raise HTTPException(
                    status_code=400,
                    detail="landing_slug must be 3-100 chars of lowercase letters, digits and hyphens "
                    "(no leading/trailing hyphen), and not a reserved word.",
                )
            if _slug_taken(db, requested, user.id):
                raise HTTPException(status_code=409, detail="That landing slug is already taken.")
            row.landing_slug = requested

    if body.show_property_fields is not None:
        row.show_property_fields = bool(body.show_property_fields)

    if body.business_type is not None:
        value = body.business_type.strip()
        if value and not business_types.is_valid_type(value):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown business_type. Valid: {sorted(business_types.BUSINESS_TYPES)}",
            )
        row.business_type = value

    db.commit()
    return {"settings": _public(row)}
