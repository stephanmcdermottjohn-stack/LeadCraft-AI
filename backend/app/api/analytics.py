"""Website analytics summary (P1 #4). Auth, tenant-scoped: reads only the
caller's first-party events. No PII is stored, so none can leak here."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import User
from app.services import analytics as svc

router = APIRouter(prefix="/api/analytics")


@router.get("/summary")
def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return svc.summary(db, user.id, days=days)
