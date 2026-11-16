"""Auth routes: register, login, me (Bearer token)."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ClientSettings, User
from app.services import auth_service

router = APIRouter(prefix="/api/auth")

EMAIL_RE_NOTE = "EmailStr validates format; uniqueness enforced in DB + handler."


class RegisterBody(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "business_name": user.business_name,
        "email": user.email,
        "plan_tier": user.plan_tier,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    uid = auth_service.verify_token(auth.removeprefix("Bearer ").strip())
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists.")
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
    return {"user": _public_user(user), "token": auth_service.issue_token(user.id)}


@router.post("/login")
def login(body: LoginBody, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not auth_service.verify_password(body.password, user.password_hash):
        # Same response for both cases: do not reveal which emails exist.
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"user": _public_user(user), "token": auth_service.issue_token(user.id)}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": _public_user(user)}
