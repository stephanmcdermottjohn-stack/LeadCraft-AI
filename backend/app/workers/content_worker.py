"""Phase 2 worker: due scheduled posts become ready_to_publish.

Honest scope (roadmap Section 4): MVP does NOT auto-publish — publishing to
Meta requires Meta app review; the worker only flips status so the dashboard
can show "ready to publish" and the user posts manually. Auto-publish is a
post-review upgrade.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContentPost


def run_due_posts_pass(db: Session) -> int:
    """Mark every scheduled post whose time has arrived as ready_to_publish.
    Returns the number of posts flipped."""
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = db.scalars(select(ContentPost).where(ContentPost.status == "scheduled")).all()
    flipped = 0
    for post in rows:
        scheduled = post.scheduled_at
        if scheduled is None:
            continue
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=datetime.timezone.utc)
        if scheduled <= now:
            post.status = "ready_to_publish"
            flipped += 1
    if flipped:
        db.commit()
    return flipped
