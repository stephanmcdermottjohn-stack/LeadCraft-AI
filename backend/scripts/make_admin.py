"""Create or promote a platform admin (Phase 3D).

Usage (from backend/):
  python scripts/make_admin.py admin@leadcraft.pk StrongPassword123

If the account exists -> promotes it (is_admin=True). Otherwise creates it.
Safe to re-run.
"""
import datetime
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

if len(sys.argv) != 3:
    sys.exit("Usage: python scripts/make_admin.py <email> <password>")

email = sys.argv[1].strip().lower()
password = sys.argv[2]

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services import auth_service  # noqa: E402

# app.db reads DATABASE_URL (from .env via load_dotenv above) at import time,
# so SessionLocal is already bound to the right database.
db = SessionLocal()

user = db.scalar(select(User).where(User.email == email))
if user:
    user.is_admin = True
    action = "promoted existing account"
else:
    user = User(
        business_name="LeadCraft Admin",
        email=email,
        password_hash=auth_service.hash_password(password),
        plan_tier="admin",
        is_admin=True,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(user)
    action = "created new admin account"
db.commit()
db.close()
print(f"{action}: {email} (is_admin=True)")
