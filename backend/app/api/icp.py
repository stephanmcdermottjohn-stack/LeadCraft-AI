"""ICP profile CRUD + lead-fit matching (roadmap P0 #2). User-scoped
throughout: cross-tenant reads/writes return 404 like every other resource.
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import IcpProfile, Lead, User
from app.services import icp as icp_service

router = APIRouter(prefix="/api/icp")


class IcpBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    industry: str = Field(default="", max_length=100)
    company_size: str = Field(default="", max_length=50)
    location: str = Field(default="", max_length=200)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    business_type: str = Field(default="", max_length=50)
    needs: str = Field(default="", max_length=1000)
    preferred_services: str = Field(default="", max_length=1000)
    decision_authority: str = Field(default="", max_length=200)
    buying_timeline: str = Field(default="", max_length=200)
    # Capped in model_post_init (more than 12 silently dropped, not a 422).
    criteria: list[str] = Field(default_factory=list)
    is_default: bool = False

    def model_post_init(self, __context) -> None:
        self.criteria = [c.strip()[:200] for c in self.criteria if c.strip()][:12]


def _public(p: IcpProfile) -> dict:
    try:
        criteria = json.loads(p.criteria_json or "[]")
        if not isinstance(criteria, list):
            criteria = []
    except ValueError:
        criteria = []
    return {
        "id": p.id,
        "name": p.name,
        "industry": p.industry,
        "company_size": p.company_size,
        "location": p.location,
        "budget_min": p.budget_min,
        "budget_max": p.budget_max,
        "business_type": p.business_type,
        "needs": p.needs,
        "preferred_services": p.preferred_services,
        "decision_authority": p.decision_authority,
        "buying_timeline": p.buying_timeline,
        "criteria": criteria,
        "is_default": bool(p.is_default),
    }


def _get_owned(db: Session, profile_id: int, user: User) -> IcpProfile:
    row = db.get(IcpProfile, profile_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="ICP profile not found.")
    return row


def _validate_business_type(value: str) -> None:
    from app.services import business_types

    if value and not business_types.is_valid_type(value):
        raise HTTPException(status_code=400, detail="Unknown business_type for the ICP profile.")
    if re.search(r"[\r\n<>]", value):
        raise HTTPException(status_code=400, detail="Invalid characters.")


@router.get("/templates")
def templates() -> dict:
    return {"templates": icp_service.template_payload()}


@router.get("")
def list_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(IcpProfile).where(IcpProfile.user_id == user.id).order_by(IcpProfile.created_at.desc())
    ).all()
    return {"profiles": [_public(p) for p in rows]}


@router.post("", status_code=201)
def create_profile(body: IcpBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _validate_business_type(body.business_type)
    if body.budget_min is not None and body.budget_max is not None and body.budget_min > body.budget_max:
        raise HTTPException(status_code=400, detail="budget_min must not exceed budget_max.")
    profile = IcpProfile(
        user_id=user.id,
        name=body.name.strip(),
        industry=body.industry.strip(),
        company_size=body.company_size.strip(),
        location=body.location.strip(),
        budget_min=body.budget_min,
        budget_max=body.budget_max,
        business_type=body.business_type,
        needs=body.needs.strip(),
        preferred_services=body.preferred_services.strip(),
        decision_authority=body.decision_authority.strip(),
        buying_timeline=body.buying_timeline.strip(),
        criteria_json=json.dumps(body.criteria),
        is_default=body.is_default,
    )
    if body.is_default:
        for row in db.scalars(select(IcpProfile).where(IcpProfile.user_id == user.id, IcpProfile.is_default)).all():
            row.is_default = False
    db.add(profile)
    db.commit()
    return {"profile": _public(profile)}


@router.patch("/{profile_id}")
def update_profile(
    profile_id: int,
    body: IcpBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _validate_business_type(body.business_type)
    if body.budget_min is not None and body.budget_max is not None and body.budget_min > body.budget_max:
        raise HTTPException(status_code=400, detail="budget_min must not exceed budget_max.")
    profile = _get_owned(db, profile_id, user)
    profile.name = body.name.strip()
    profile.industry = body.industry.strip()
    profile.company_size = body.company_size.strip()
    profile.location = body.location.strip()
    profile.budget_min = body.budget_min
    profile.budget_max = body.budget_max
    profile.business_type = body.business_type
    profile.needs = body.needs.strip()
    profile.preferred_services = body.preferred_services.strip()
    profile.decision_authority = body.decision_authority.strip()
    profile.buying_timeline = body.buying_timeline.strip()
    profile.criteria_json = json.dumps(body.criteria)
    if body.is_default:
        for row in db.scalars(select(IcpProfile).where(IcpProfile.user_id == user.id, IcpProfile.is_default)).all():
            if row.id != profile.id:
                row.is_default = False
    profile.is_default = body.is_default
    db.commit()
    return {"profile": _public(profile)}


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    profile = _get_owned(db, profile_id, user)
    db.delete(profile)
    db.commit()


@router.post("/{profile_id}/match/{lead_id}")
def match_profile(
    profile_id: int,
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = _get_owned(db, profile_id, user)
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        raise HTTPException(status_code=404, detail="Lead not found.")
    fit = icp_service.match_lead(_public(profile), {
        "area": lead.area,
        "intent_notes": lead.intent_notes,
        "metadata": _lead_metadata(lead),
    })
    return {"lead_id": lead.id, "profile_id": profile.id, "fit": fit}


def _lead_metadata(lead: Lead) -> dict:
    try:
        parsed = json.loads(lead.metadata_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}
