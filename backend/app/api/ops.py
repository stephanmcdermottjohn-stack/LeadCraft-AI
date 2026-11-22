"""Data, audit & ops (P5 #2).

Owner/admin only: the export contains customer contact data, the audit log
contains team actions, and retention is irreversible. Agents and viewers get
403; unauthenticated calls get 401. Every route is tenant-scoped.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import User
from app.services import audit as audit_svc
from app.services import ops as svc

router = APIRouter(prefix="/api/ops")

OPS_ROLES = ("owner", "admin")


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_ops(user: User) -> None:
    if _role(user) not in OPS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Owner or admin role required for export, audit and retention.",
        )


class PurgeBody(BaseModel):
    days: int = Field(default=90, ge=svc.RETENTION_MIN_DAYS, le=svc.RETENTION_MAX_DAYS)
    confirm: bool = False


@router.get("/usage")
def get_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_ops(user)
    return svc.usage(db, user)


@router.get("/export")
def export_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ops(user)
    payload = svc.workspace_export(db, user)
    audit_svc.record(
        db,
        user,
        "ops.export",
        target_type="workspace",
        target_id=user.id,
        detail={"counts": payload["counts"], "truncated": payload["truncated_tables"]},
    )
    db.commit()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="leadcraft-workspace-{user.id}-{stamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/audit")
def list_audit(
    action: str = "",
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_ops(user)
    limit = max(1, min(limit, 500))
    rows = audit_svc.list_rows(db, user.id, action.strip(), limit)
    return {
        "entries": [audit_svc.public(r) for r in rows],
        "count": len(rows),
        "actions": audit_svc.actions(db, user.id),
        "scope": "Workspace-level admin actions only. Lead edits live in each lead's timeline.",
        "append_only": True,
    }


@router.get("/retention/preview")
def retention_preview(
    days: int = Query(default=90, ge=svc.RETENTION_MIN_DAYS, le=svc.RETENTION_MAX_DAYS),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_ops(user)
    return svc.retention_preview(db, user.id, days)


@router.post("/retention/purge")
def retention_purge(
    body: PurgeBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_ops(user)
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to delete telemetry. Run the preview first.",
        )
    result = svc.retention_purge(db, user.id, body.days)
    audit_svc.record(
        db,
        user,
        "ops.retention_purged",
        target_type="telemetry",
        detail={"days": result["days"], "deleted": result["deleted"]},
    )
    db.commit()
    return result
