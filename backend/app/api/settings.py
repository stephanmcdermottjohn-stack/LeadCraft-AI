"""Client settings routes — the personalization source for content prompts."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import ClientSettings, User

router = APIRouter(prefix="/api/settings")


class SettingsBody(BaseModel):
    niche: str = Field(default="", max_length=200)
    target_area: str = Field(default="", max_length=200)
    brand_voice: str = Field(default="", max_length=500)


def _public(s: ClientSettings) -> dict:
    return {
        "niche": s.niche,
        "target_area": s.target_area,
        "brand_voice": s.brand_voice,
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
    row.niche = body.niche.strip()
    row.target_area = body.target_area.strip()
    row.brand_voice = body.brand_voice.strip()
    db.commit()
    return {"settings": _public(row)}
