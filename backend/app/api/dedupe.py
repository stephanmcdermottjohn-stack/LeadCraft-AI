"""Duplicate lead detection & safe merge (P6 #1 v1).

Reads are available to every authenticated role (own workspace only). The
merge itself deletes lead rows after moving their history, so it is restricted
to **owner/admin** - agents and viewers get 403. Unauthenticated calls get 401,
and another workspace's lead gets 404.

No third-party service, no fuzzy matching, no schema changes: detection uses
normalized phone/email values and every child table is reassigned before the
duplicate row is deleted.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import User
from app.services import dedupe as svc

router = APIRouter(prefix="/api/leads")

MERGE_ROLES = ("owner", "admin")


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_merge(user: User) -> None:
    if _role(user) not in MERGE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Owner or admin role required to merge leads.",
        )


class MergeBody(BaseModel):
    primary_id: int = Field(gt=0)
    duplicate_ids: list[int] = Field(min_length=1, max_length=svc.MERGE_LIMIT)
    dry_run: bool = False


@router.get("/duplicates")
def duplicate_groups(
    limit: int = Query(default=50, ge=1, le=svc.GROUP_LIMIT),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return svc.find_groups(db, user, limit=limit)


@router.get("/{lead_id}/duplicates")
def lead_duplicates(
    lead_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = svc.duplicates_for_lead(db, user, lead_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return payload


@router.post("/merge")
def merge_leads(
    body: MergeBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_merge(user)
    try:
        return svc.merge(db, user, body.primary_id, body.duplicate_ids, dry_run=body.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        missing = ", ".join(str(item) for item in exc.args[0]) if exc.args else "unknown"
        raise HTTPException(
            status_code=404,
            detail=f"Lead(s) not found in this workspace: {missing}",
        ) from exc
