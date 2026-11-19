"""Team members & roles (P3 #1) - additive to the existing `User = workspace`
tenancy.

An active member's session is resolved to the workspace owner `User`, so all
existing `user.id` scoping keeps working untouched; this module supplies the
role. Invites are token-based links - the platform never sends email, and an
account that already owns leads cannot be silently re-scoped into someone
else's workspace.
"""
import datetime
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Lead, User, WorkspaceMember

ROLES = ("admin", "manager", "agent", "viewer")
OWNER = "owner"
STATUSES = ("invited", "active", "removed")
TEAM_MANAGERS = ("owner", "admin")
CONFIG_ROLES = ("owner", "admin", "manager")


class TeamError(Exception):
    """Raised with a message + HTTP status for the API layer."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def active_membership(db: Session, account_id: int) -> WorkspaceMember | None:
    return db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.member_user_id == account_id,
            WorkspaceMember.status == "active",
        )
    )


def resolve_workspace(db: Session, account: User) -> tuple[User, str, WorkspaceMember | None]:
    """Return (data-scope user, role, membership row or None).

    Owner accounts resolve to themselves with role 'owner'. An active member
    resolves to the owner account so every existing endpoint inherits the
    workspace scope without a schema change.
    """
    row = active_membership(db, account.id)
    if row is None:
        return account, OWNER, None
    owner = db.get(User, row.owner_user_id)
    if owner is None:
        # Owner deleted: never inherit a dangling scope.
        return account, OWNER, None
    return owner, row.role, row


def can_manage_team(role: str) -> bool:
    return role in TEAM_MANAGERS


def can_write(role: str) -> bool:
    return role != "viewer"


def can_change_config(role: str) -> bool:
    return role in CONFIG_ROLES


def owns_data(db: Session, account_id: int) -> bool:
    """True when the account already has leads of its own.

    Re-scoping such an account into a teammate slot would hide its own
    workspace, so invites and acceptance are refused instead of guessing.
    """
    count = db.scalar(select(func.count(Lead.id)).where(Lead.user_id == account_id))
    return bool(count)


def _new_token(db: Session) -> str:
    for _ in range(8):
        token = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
        if db.scalar(select(WorkspaceMember.id).where(WorkspaceMember.invite_token == token)) is None:
            return token
    raise TeamError("Could not allocate an invite token - please retry.", 503)


def invite(db: Session, owner: User, email: str, role: str) -> WorkspaceMember:
    email = _norm_email(email)
    role = (role or "").strip().lower()
    if not email:
        raise TeamError("Email is required.")
    if role not in ROLES:
        raise TeamError(f"role must be one of: {', '.join(ROLES)}")
    if email == owner.email.lower():
        raise TeamError("You cannot invite your own account.")

    existing_account = db.scalar(select(User).where(User.email == email))
    if existing_account is not None:
        if existing_account.id == owner.id:
            raise TeamError("You cannot invite your own account.")
        if owns_data(db, existing_account.id):
            raise TeamError(
                "That account already has its own leads, so it cannot join as a teammate. "
                "Invite a different email address instead.",
                409,
            )
        other = active_membership(db, existing_account.id)
        if other is not None and other.owner_user_id != owner.id:
            raise TeamError("That account is already an active member of another workspace.", 409)

    row = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.owner_user_id == owner.id,
            WorkspaceMember.invited_email == email,
        )
    )
    if row is not None and row.status == "active":
        raise TeamError("That email is already an active member of this workspace.", 409)

    if row is None:
        row = WorkspaceMember(owner_user_id=owner.id, invited_email=email)
        db.add(row)
    # Re-invite: rotate the token so an old link stops working.
    row.role = role
    row.status = "invited"
    row.member_user_id = existing_account.id if existing_account is not None else None
    row.invite_token = _new_token(db)
    row.accepted_at = None
    db.flush()
    return row


def accept(db: Session, account: User, token: str) -> WorkspaceMember:
    token = (token or "").strip()
    if not token:
        raise TeamError("Invite token is required.")
    row = db.scalar(select(WorkspaceMember).where(WorkspaceMember.invite_token == token))
    if row is None or row.status != "invited":
        raise TeamError("Invalid or already used invite token.", 404)
    if row.invited_email != account.email.lower():
        raise TeamError("This invite belongs to a different email address.", 403)
    if row.owner_user_id == account.id:
        raise TeamError("You cannot accept an invite to your own workspace.")
    if owns_data(db, account.id):
        raise TeamError(
            "This account already has its own leads, so it cannot join as a teammate.", 409
        )
    other = active_membership(db, account.id)
    if other is not None:
        raise TeamError("This account is already an active member of a workspace.", 409)

    row.member_user_id = account.id
    row.status = "active"
    row.accepted_at = datetime.datetime.now(datetime.timezone.utc)
    db.flush()
    return row


def change_role(db: Session, row: WorkspaceMember, actor_account_id: int, role: str) -> WorkspaceMember:
    role = (role or "").strip().lower()
    if role not in ROLES:
        raise TeamError(f"role must be one of: {', '.join(ROLES)}")
    if row.status == "removed":
        raise TeamError("This member was removed - invite them again first.")
    if row.member_user_id is not None and row.member_user_id == actor_account_id:
        raise TeamError("You cannot change your own role.")
    row.role = role
    db.flush()
    return row


def remove(db: Session, row: WorkspaceMember, actor_account_id: int) -> WorkspaceMember:
    if row.status == "removed":
        return row
    if row.member_user_id is not None and row.member_user_id == actor_account_id:
        raise TeamError("You cannot remove yourself.")
    row.status = "removed"
    row.member_user_id = None
    row.invite_token = None
    db.flush()
    return row
