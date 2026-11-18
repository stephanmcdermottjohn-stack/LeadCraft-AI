"""Landing A/B variants (P1 #1). User-scoped CRUD + an honest report.

Report arms: "control" (business defaults, no row) plus every variant ever
created (inactive arms keep their historical numbers — deactivating never
deletes data). Submission/qualified counts come from leads.landing_variant;
impressions from landing_events. Where data is genuinely missing (e.g. a
variant never served) the report says so instead of showing a fake 0%.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, LandingEvent, LandingVariant, Lead, User

router = APIRouter(prefix="/api/landing-variants")

CONTROL = "control"
MAX_VARIANTS = 5
LABEL_RE = re.compile(r"^[A-Za-z0-9-]{1,50}$")


class VariantBody(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    headline: str = Field(default="", max_length=300)
    subtext: str = Field(default="", max_length=2000)
    cta_label: str = Field(default="", max_length=100)
    is_active: bool = True

    def model_post_init(self, __context) -> None:
        self.label = self.label.strip()
        self.headline = self.headline.strip()
        self.subtext = self.subtext.strip()
        self.cta_label = self.cta_label.strip()
        if not LABEL_RE.fullmatch(self.label) or self.label.lower() == CONTROL:
            raise ValueError("label must be 1-50 chars of letters/digits/hyphens and not 'control'")


def _public(v: LandingVariant) -> dict:
    return {
        "id": v.id,
        "label": v.label,
        "headline": v.headline,
        "subtext": v.subtext,
        "cta_label": v.cta_label,
        "is_active": bool(v.is_active),
    }


def _get_owned(db: Session, variant_id: int, user: User) -> LandingVariant:
    row = db.get(LandingVariant, variant_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Variant not found.")
    return row


def _slug(db: Session, user: User) -> str:
    row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    return row.landing_slug if row and row.landing_slug else ""


@router.get("")
def list_variants(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(LandingVariant).where(LandingVariant.user_id == user.id).order_by(LandingVariant.id.asc())
    ).all()
    return {"variants": [_public(v) for v in rows]}


@router.post("", status_code=201)
def create_variant(
    body: VariantBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    existing = db.scalars(select(LandingVariant).where(LandingVariant.user_id == user.id)).all()
    if len(existing) >= MAX_VARIANTS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_VARIANTS} variants per business.")
    if any(v.label.lower() == body.label.lower() for v in existing):
        raise HTTPException(status_code=409, detail=f"Variant '{body.label}' already exists.")
    row = LandingVariant(
        user_id=user.id, label=body.label, headline=body.headline,
        subtext=body.subtext, cta_label=body.cta_label, is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    return {"variant": _public(row)}


@router.patch("/{variant_id}")
def update_variant(
    variant_id: int, body: VariantBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    row = _get_owned(db, variant_id, user)
    clash = db.scalar(
        select(LandingVariant).where(
            LandingVariant.user_id == user.id,
            func.lower(LandingVariant.label) == body.label.lower(),
            LandingVariant.id != row.id,
        )
    )
    if clash is not None:
        raise HTTPException(status_code=409, detail=f"Variant '{body.label}' already exists.")
    # History note: the report keys on label — renaming a served arm breaks
    # attribution continuity, so renames are not offered (label is fixed by
    # replacement semantics: if the label changes, we refuse).
    if body.label != row.label:
        raise HTTPException(status_code=400, detail="Variant label is fixed after creation (rename would orphan past traffic).")
    row.headline, row.subtext, row.cta_label = body.headline, body.subtext, body.cta_label
    row.is_active = body.is_active
    db.commit()
    return {"variant": _public(row)}


@router.delete("/{variant_id}", status_code=204)
def delete_variant(variant_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    row = _get_owned(db, variant_id, user)
    db.delete(row)
    db.commit()


@router.get("/report")
def ab_report(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    slug = _slug(db, user)
    variants = db.scalars(select(LandingVariant).where(LandingVariant.user_id == user.id)).all()
    arms = [(CONTROL, "Control (business defaults)")] + [(v.label, f"Variant {v.label}") for v in variants]

    imp_rows = (
        db.execute(
            select(LandingEvent.variant, func.count())
            .where(LandingEvent.user_id == user.id, LandingEvent.slug == slug)
            .group_by(LandingEvent.variant)
        ).all()
        if slug else []
    )
    impressions = {variant: count for variant, count in imp_rows}

    lead_rows = (
        db.execute(
            select(Lead.landing_variant, func.count())
            .where(Lead.user_id == user.id)
            .group_by(Lead.landing_variant)
        ).all()
    )
    submissions = {variant: count for variant, count in lead_rows}

    qual_rows = (
        db.execute(
            select(Lead.landing_variant, func.count())
            .where(
                Lead.user_id == user.id,
                (Lead.lifecycle_stage != "capture") | (Lead.score > 0),
            )
            .group_by(Lead.landing_variant)
        ).all()
    )
    qualified = {variant: count for variant, count in qual_rows}

    report = []
    for label, display in arms:
        imp, sub, qual = impressions.get(label, 0), submissions.get(label, 0), qualified.get(label, 0)
        if imp == 0 and sub == 0:
            note = "No traffic served to this arm yet - conversion rate unknown (not 0%)."
            rate = None
        elif imp < 30:
            note = f"Only {imp} impression(s) - too early to compare arms."
            rate = None
        else:
            rate = round(sub / imp * 100, 1)
            note = ""
        report.append({
            "arm": label, "display": display,
            "impressions": imp, "submissions": sub, "qualified": qual,
            "submission_rate_pct": rate, "note": note,
        })
    return {"slug": slug, "arms": report}
