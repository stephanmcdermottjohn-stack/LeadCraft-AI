"""Team endpoints (P3 #1) - invites, roles, removal. No email is ever sent.

Auth: every route requires a session. Team management routes require the
owner or an admin role; the invited person accepts with their own account.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import User, WorkspaceMember
from app.services import audit as audit_svc
from app.services import team as svc

router = APIRouter(prefix="/api/team")


class InviteBody(BaseModel):
    email: EmailStr
    role: str = Field(default="agent", max_length=20)


class RoleBody(BaseModel):
    role: str = Field(min_length=1, max_length=20)


class AcceptBody(BaseModel):
    token: str = Field(min_length=4, max_length=64)


def _role(user: User) -> str:
    return getattr(user, "workspace_role", svc.OWNER)


def _account_id(user: User) -> int:
    return getattr(user, "workspace_account_id", user.id)


def _require_manager(user: User) -> None:
    if not svc.can_manage_team(_role(user)):
        raise HTTPException(status_code=403, detail="Owner or admin role required.")


def _public(row: WorkspaceMember, show_token: bool) -> dict:
    return {
        "id": row.id,
        "email": row.invited_email,
        "role": row.role,
        "status": row.status,
        "member_user_id": row.member_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        # Only the owner/admin sees the link; it is a single-use secret.
        "invite_path": (
            f"/settings?invite={row.invite_token}"
            if show_token and row.status == "invited" and row.invite_token
            else None
        ),
    }


@router.get("")
def list_team(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    role = _role(user)
    rows = db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.owner_user_id == user.id)
        .order_by(WorkspaceMember.created_at.asc())
    ).all()
    show_token = svc.can_manage_team(role)
    return {
        "workspace": {
            "owner_id": user.id,
            "business_name": user.business_name,
            "plan_tier": user.plan_tier,
        },
        "my_role": role,
        "owner": {"email": user.email, "role": svc.OWNER, "status": "active"},
        "members": [_public(r, show_token) for r in rows],
        "seats_note": "Team seats are manually managed; no billing system enforces them.",
    }


@router.post("/invite", status_code=201)
def invite(
    body: InviteBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _require_manager(user)
    try:
        row = svc.invite(db, user, body.email, body.role)
    except svc.TeamError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    audit_svc.record(
        db, user, "team.invited", "member", row.id, {"email": row.invited_email, "role": row.role}
    )
    db.commit()
    return {"member": _public(row, True)}


@router.post("/accept")
def accept(
    body: AcceptBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    account = db.get(User, _account_id(user))
    if account is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")
    try:
        row = svc.accept(db, account, body.token)
    except svc.TeamError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    # Recorded in the joined workspace, attributed to the invitee (not the owner).
    audit_svc.record_for(
        db,
        workspace_id=row.owner_user_id,
        actor_user_id=account.id,
        actor_email_value=account.email,
        action="team.joined",
        target_type="member",
        target_id=row.id,
        detail={"role": row.role},
    )
    db.commit()
    return {
        "member": _public(row, False),
        "note": "Workspace joined. Reload the app to switch to the shared workspace.",
    }


@router.patch("/{member_id}")
def update_role(
    member_id: int,
    body: RoleBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(user)
    row = db.get(WorkspaceMember, member_id)
    if row is None or row.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Team member not found.")
    old_role = row.role
    try:
        svc.change_role(db, row, _account_id(user), body.role)
    except svc.TeamError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    audit_svc.record(
        db,
        user,
        "team.role_changed",
        "member",
        row.id,
        {"email": row.invited_email, "from": old_role, "to": row.role},
    )
    db.commit()
    return {"member": _public(row, True)}


@router.delete("/{member_id}", status_code=204)
def remove_member(
    member_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    _require_manager(user)
    row = db.get(WorkspaceMember, member_id)
    if row is None or row.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Team member not found.")
    old_role = row.role
    try:
        svc.remove(db, row, _account_id(user))
    except svc.TeamError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    audit_svc.record(
        db,
        user,
        "team.removed",
        "member",
        row.id,
        {"email": row.invited_email, "role": old_role},
    )
    db.commit()
