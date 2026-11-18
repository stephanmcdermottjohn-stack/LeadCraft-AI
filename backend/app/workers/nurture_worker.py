"""Nurture worker (P1 #2): advance active enrollments whose next touch is due.

Honest scope (zero external cost): due touches surface as the lead's
next_action + a timeline activity — nothing is sent anywhere.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NurtureEnrollment
from app.services import nurture as svc


def run_due_pass(db: Session) -> int:
    """Global pass (all users). Returns the number of touches surfaced."""
    return svc.process_due(db, user_id=None)
