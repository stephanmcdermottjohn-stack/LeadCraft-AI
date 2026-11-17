"""Platform-admin routes (Phase 3D).

Admins are platform staff, NOT client accounts: they can read aggregate
platform stats but never another business's individual leads (privacy rule —
lead rows stay strictly user-scoped everywhere else in the API).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db import get_db
from app.models import Lead, User

router = APIRouter(prefix="/api/admin")


@router.get("/overview")
def overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_leads = db.scalar(select(func.count(Lead.id))) or 0

    by_status = dict(db.execute(select(Lead.status, func.count(Lead.id)).group_by(Lead.status)).all())
    by_source = dict(db.execute(select(Lead.source, func.count(Lead.id)).group_by(Lead.source)).all())

    recent = db.scalars(select(User).order_by(User.created_at.desc()).limit(20)).all()
    lead_counts = dict(
        db.execute(
            select(Lead.user_id, func.count(Lead.id)).group_by(Lead.user_id)
        ).all()
    )
    recent_users = [
        {
            "id": u.id,
            "business_name": u.business_name,
            "email": u.email,
            "plan_tier": u.plan_tier,
            "lead_count": lead_counts.get(u.id, 0),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in recent
    ]
    return {
        "total_users": total_users,
        "total_leads": total_leads,
        "leads_by_status": by_status,
        "leads_by_source": by_source,
        "recent_users": recent_users,
    }
