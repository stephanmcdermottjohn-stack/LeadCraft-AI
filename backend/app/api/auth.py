"""Auth routes: register, login, me (Bearer token)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClientSettings, User
from app.services import auth_service
from app.services import team as team_service

router = APIRouter(prefix="/api/auth")

EMAIL_RE_NOTE = "EmailStr validates format; uniqueness enforced in DB + handler."

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# A viewer may still log in / read their own session.
VIEWER_WRITE_EXEMPT = ("/api/auth",)
# Business configuration an agent cannot change (operational writes stay open).
AGENT_CONFIG_PREFIXES = ("/api/settings", "/api/landing-ab", "/api/campaign-spend", "/api/billing")


class RegisterBody(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _public_user(user: User, *, role: str = "owner", account: User | None = None) -> dict:
    """Session payload. `user` is the data-scope account (workspace owner);
    `account` is the logged-in identity (differs for team members)."""
    account = account or user
    is_member = account.id != user.id
    return {
        "id": user.id,
        "business_name": user.business_name,
        "email": account.email,
        "plan_tier": user.plan_tier,
        "is_admin": bool(user.is_admin),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "role": role,
        "workspace_owner_id": user.id,
        "workspace_owner_email": user.email,
        "is_workspace_member": is_member,
    }


def build_session_user(db: Session, account: User) -> dict:
    owner, role, membership = team_service.resolve_workspace(db, account)
    return _public_user(owner, role=role, account=account)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    uid = auth_service.verify_token(auth.removeprefix("Bearer ").strip())
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    account = db.get(User, uid)
    if account is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")

    # Team resolution (P3 #1): an active member is scoped to the workspace
    # owner, so every existing `user.id` query keeps working unchanged.
    owner, role, membership = team_service.resolve_workspace(db, account)
    owner.workspace_role = role  # transient, not a DB column
    owner.workspace_account_id = account.id
    owner.workspace_member_id = membership.id if membership else None

    if request.method not in SAFE_METHODS:
        path = request.url.path
        if role == "viewer" and not path.startswith(VIEWER_WRITE_EXEMPT):
            raise HTTPException(
                status_code=403, detail="Viewer role is read-only - ask an owner or admin to change your role."
            )
        if role == "agent" and path.startswith(AGENT_CONFIG_PREFIXES):
            raise HTTPException(
                status_code=403, detail="Your role cannot change business settings."
            )
    return owner


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


@router.post("/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == body.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        business_name=body.business_name.strip(),
        email=body.email.lower(),
        password_hash=auth_service.hash_password(body.password),
        plan_tier="basic",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(ClientSettings(user_id=user.id))
    db.commit()
    return {"user": build_session_user(db, user), "token": auth_service.issue_token(user.id)}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not auth_service.verify_password(body.password, user.password_hash):
        # Same response for both cases: do not reveal which emails exist.
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"user": build_session_user(db, user), "token": auth_service.issue_token(user.id)}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(User, getattr(user, "workspace_account_id", user.id)) or user
    return {"user": build_session_user(db, account)}
