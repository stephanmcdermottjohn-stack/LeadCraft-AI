"""Funnel + campaign report endpoints (P1 #5). Auth, tenant-scoped."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import User
from app.services import reports as svc

router = APIRouter(prefix="/api/reports")


@router.get("/funnel")
def funnel_report(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return svc.funnel_report(db, user.id, days=days)
