"""Workspace audit log (P5 #2) - append-only, no secrets.

Only high-value administrative actions are recorded here: workspace settings,
team permissions, the manual billing ledger, data export and retention purges.
Lead-level edits keep their own trail (`lead_stage_history`, `lead_activities`),
so this log stays small and readable.

Rules:
- `detail_json` holds keys/counts/labels only - never passwords, tokens or
  customer message bodies. `_clean` caps the payload size.
- Callers add the row inside the same transaction as the change, then commit.
- There is no update/delete endpoint: the log is append-only by design.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User

MAX_DETAIL = 2000


def actor_account_id(user: User) -> int:
    """The real logged-in account id (members are scoped to the workspace owner)."""
    return int(getattr(user, "workspace_account_id", None) or user.id)


def actor_email(db: Session, user: User) -> str:
    account_id = actor_account_id(user)
    account = db.get(User, account_id)
    return ((account.email if account else user.email) or "")[:320]


def record(
    db: Session,
    user: User,
    action: str,
    target_type: str = "",
    target_id: str | int = "",
    detail: dict | None = None,
) -> AuditLog:
    """Queue an audit row in the current transaction (caller commits)."""
    return record_for(
        db,
        workspace_id=user.id,
        actor_user_id=actor_account_id(user),
        actor_email_value=actor_email(db, user),
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )


def record_for(
    db: Session,
    *,
    workspace_id: int,
    actor_user_id: int | None,
    actor_email_value: str,
    action: str,
    target_type: str = "",
    target_id: str | int = "",
    detail: dict | None = None,
) -> AuditLog:
    """Explicit-actor variant (used when the action targets a different workspace)."""
    payload = json.dumps(detail or {}, ensure_ascii=False, default=str)
    if len(payload) > MAX_DETAIL:
        payload = json.dumps({"truncated": True}, ensure_ascii=False)
    row = AuditLog(
        user_id=workspace_id,
        actor_user_id=actor_user_id,
        actor_email=(actor_email_value or "")[:320],
        action=(action or "")[:60],
        target_type=(target_type or "")[:40],
        target_id=str(target_id or "")[:60],
        detail_json=payload,
    )
    db.add(row)
    return row


def public(row: AuditLog) -> dict:
    try:
        detail = json.loads(row.detail_json or "{}")
    except ValueError:
        detail = {}
    return {
        "id": row.id,
        "actor_email": row.actor_email,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "detail": detail,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_rows(db: Session, user_id: int, action: str = "", limit: int = 100) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()


def actions(db: Session, user_id: int) -> list[str]:
    rows = db.scalars(select(AuditLog.action).where(AuditLog.user_id == user_id).distinct()).all()
    return sorted({r for r in rows if r})
