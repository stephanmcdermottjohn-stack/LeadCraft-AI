"""Content generation & scheduling routes (Phase 2)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.integrations import llm
from app.api.auth import get_current_user
from app.models import ClientSettings, ContentPost, User

router = APIRouter(prefix="/api/content")

PLATFORMS = {"facebook", "instagram", "tiktok", "whatsapp_status", "other"}
POST_STATUSES = {"draft", "scheduled", "ready_to_publish", "published"}


class GenerateBody(BaseModel):
    platform: str = Field(default="facebook")
    tone: str = Field(default="friendly", max_length=100)
    count: int = Field(default=3, ge=1, le=5)


class ScheduleBody(BaseModel):
    content_text: str = Field(min_length=1, max_length=5000)
    platform: str = Field(default="facebook")
    scheduled_at: datetime.datetime | None = None
    media_url: str | None = Field(default=None, max_length=1000)


def _public_post(post: ContentPost) -> dict:
    return {
        "id": post.id,
        "platform": post.platform,
        "content_text": post.content_text,
        "media_url": post.media_url,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "status": post.status,
        "created_at": post.created_at.isoformat() if post.created_at else None,
    }


@router.post("/generate")
def generate(body: GenerateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if body.platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform must be one of: {sorted(PLATFORMS)}")
    settings_row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    settings_row = settings_row or ClientSettings(user_id=user.id)
    req = llm.ContentRequest(
        business_name=user.business_name,
        niche=settings_row.niche,
        target_area=settings_row.target_area,
        brand_voice=settings_row.brand_voice,
        platform=body.platform,
        tone=body.tone,
        count=body.count,
    )
    settings = get_settings()
    try:
        result = llm.generate_options(req, settings.llm_provider, settings.gemini_api_key, settings.gemini_model)
    except llm.LLMError as exc:
        # A configured provider failing must surface honestly, never silently
        # fall back to mock (the user asked for real AI output).
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    return {"provider": result["provider"], "notice": result["notice"], "options": result["options"]}


@router.post("/schedule", status_code=201)
def schedule(body: ScheduleBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if body.platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform must be one of: {sorted(PLATFORMS)}")
    status = "scheduled" if body.scheduled_at else "draft"
    post = ContentPost(
        user_id=user.id,
        platform=body.platform,
        content_text=body.content_text,
        media_url=body.media_url,
        scheduled_at=body.scheduled_at,
        status=status,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(post)
    db.commit()
    return {"post": _public_post(post)}


@router.get("/posts")
def list_posts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(ContentPost)
        .where(ContentPost.user_id == user.id)
        .order_by(ContentPost.created_at.desc())
        .limit(100)
    ).all()
    return {"posts": [_public_post(p) for p in rows]}
