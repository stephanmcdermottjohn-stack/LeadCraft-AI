"""P7 #1: custom landing pages (block builder) - owner-scoped CRUD.

Any authenticated workspace member can read their pages; writes are blocked for
viewers (global gate) and agents (agent config prefixes in app.api.auth).
Public access lives in ``GET /api/public/pages/{slug}`` and only returns
published pages.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import LandingPage, User
from app.services import audit as audit_svc
from app.services import pages as pages_svc

router = APIRouter(prefix="/api/pages")


class PageCreateBody(BaseModel):
    slug: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    blocks: list[dict] = Field(default_factory=list)
    is_published: bool = False


class PageUpdateBody(BaseModel):
    # None = keep the current value.
    slug: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, max_length=200)
    blocks: list[dict] | None = None
    is_published: bool | None = None


def _public(page: LandingPage) -> dict:
    return {
        "id": page.id,
        "slug": page.slug,
        "title": page.title,
        "blocks": pages_svc.blocks_from_json(page.blocks_json),
        "is_published": bool(page.is_published),
        "public_path": f"/p/{page.slug}",
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }


def _owned(db: Session, page_id: int, user: User) -> LandingPage:
    row = db.get(LandingPage, page_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Page not found.")
    return row


def _normalize_slug(raw: str) -> str:
    slug = (raw or "").strip().lower()
    problem = pages_svc.slug_error(slug)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    return slug


def _slug_taken(db: Session, slug: str, exclude_id: int | None = None) -> bool:
    row = db.scalar(select(LandingPage).where(LandingPage.slug == slug))
    return row is not None and row.id != exclude_id


def _validate_blocks(raw: list[dict]) -> list[dict]:
    try:
        return pages_svc.sanitize_blocks(raw)
    except pages_svc.PageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_pages(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(LandingPage).where(LandingPage.user_id == user.id).order_by(LandingPage.updated_at.desc())
    ).all()
    return {"pages": [_public(p) for p in rows], "limit": pages_svc.MAX_PAGES}


@router.post("", status_code=201)
def create_page(
    body: PageCreateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    existing = db.scalars(select(LandingPage).where(LandingPage.user_id == user.id)).all()
    if len(existing) >= pages_svc.MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"At most {pages_svc.MAX_PAGES} pages per workspace.")
    slug = _normalize_slug(body.slug)
    if _slug_taken(db, slug):
        raise HTTPException(status_code=409, detail="That page slug is already taken.")
    blocks = _validate_blocks(body.blocks)
    row = LandingPage(
        user_id=user.id,
        slug=slug,
        title=body.title.strip(),
        blocks_json=pages_svc.blocks_to_json(blocks),
        is_published=bool(body.is_published),
    )
    db.add(row)
    db.flush()
    audit_svc.record(db, user, "page.created", "landing_page", row.id,
                     {"slug": slug, "blocks": len(blocks), "published": bool(row.is_published)})
    db.commit()
    return {"page": _public(row)}


@router.patch("/{page_id}")
def update_page(
    page_id: int, body: PageUpdateBody,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict:
    row = _owned(db, page_id, user)
    if body.slug is not None:
        slug = _normalize_slug(body.slug)
        if _slug_taken(db, slug, exclude_id=row.id):
            raise HTTPException(status_code=409, detail="That page slug is already taken.")
        row.slug = slug
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="title is required.")
        row.title = title
    if body.blocks is not None:
        row.blocks_json = pages_svc.blocks_to_json(_validate_blocks(body.blocks))
    if body.is_published is not None:
        row.is_published = bool(body.is_published)
    changed = sorted(k for k, v in body.model_dump(exclude_unset=True).items() if v is not None)
    audit_svc.record(db, user, "page.updated", "landing_page", row.id,
                     {"slug": row.slug, "keys": changed})
    db.commit()
    return {"page": _public(row)}


@router.delete("/{page_id}", status_code=204)
def delete_page(page_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    row = _owned(db, page_id, user)
    audit_svc.record(db, user, "page.deleted", "landing_page", row.id, {"slug": row.slug})
    db.delete(row)
    db.commit()
