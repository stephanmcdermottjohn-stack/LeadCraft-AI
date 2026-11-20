"""Client settings routes — the personalization source for content prompts."""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, User
from app.services import business_types
from app.services import scoring as scoring_service

router = APIRouter(prefix="/api/settings")

# Public URL slugs: lowercase letters/digits with inner hyphens, 3-100 chars.
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$")
RESERVED_SLUGS = {"api", "admin", "login", "register", "settings", "leads", "public", "l"}
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    # P0 #5: engagement-score weights. Omitted = keep; {} = reset to defaults.
    # Unknown keys are dropped; values clamped to 0..100 (never a 422 surprise).
    scoring_weights: dict[str, int] | None = None
    # P3 #2 white-label branding (presentation only).
    brand_name: str | None = Field(default=None, max_length=200)
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=20)
    support_email: str | None = Field(default=None, max_length=320)
    footer_text: str | None = Field(default=None, max_length=300)
    hide_platform_brand: bool | None = None


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
        "scoring_weights": scoring_service.effective_weights(s),
        "brand_name": s.brand_name or "",
        "logo_url": s.logo_url or "",
        "primary_color": s.primary_color or "",
        "support_email": s.support_email or "",
        "footer_text": s.footer_text or "",
        "hide_platform_brand": bool(s.hide_platform_brand),
        "white_label_note": "Presentation only - no custom domain and no plan enforcement. "
        "The platform brand is hidden on your landing page and dashboard header when enabled.",
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

    if body.scoring_weights is not None:
        sanitized = scoring_service.sanitize_weights(body.scoring_weights)
        row.scoring_weights_json = json.dumps(sanitized)

    # P3 #2 white-label branding: presentation only. Colours and logo URLs are
    # validated so the landing page never renders javascript:/data: payloads.
    if body.brand_name is not None:
        row.brand_name = body.brand_name.strip()
    if body.logo_url is not None:
        value = body.logo_url.strip()
        if value and not (value.startswith("https://") or value.startswith("http://") or value.startswith("/")):
            raise HTTPException(
                status_code=400,
                detail="logo_url must be an absolute http(s) URL or a path starting with '/'.",
            )
        if any(ch.isspace() for ch in value):
            raise HTTPException(status_code=400, detail="logo_url cannot contain spaces.")
        row.logo_url = value
    if body.primary_color is not None:
        value = body.primary_color.strip()
        if value and not COLOR_RE.fullmatch(value):
            raise HTTPException(status_code=400, detail="primary_color must be a hex colour like #0ea5e9.")
        row.primary_color = value.lower()
    if body.support_email is not None:
        value = body.support_email.strip()
        if value and not EMAIL_RE.fullmatch(value):
            raise HTTPException(status_code=400, detail="support_email must be a valid email address.")
        row.support_email = value
    if body.footer_text is not None:
        row.footer_text = body.footer_text.strip()
    if body.hide_platform_brand is not None:
        row.hide_platform_brand = bool(body.hide_platform_brand)

    db.commit()
    return {"settings": _public(row)}
