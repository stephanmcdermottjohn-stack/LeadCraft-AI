"""First-party website analytics (P1 #4).

Design rules:
- Zero cookies. The landing page keeps an opaque random session id in
  sessionStorage (gone when the tab closes) and posts events to a public,
  tenant-resolving endpoint.
- No PII: no IPs, no user agent strings, no full referrers. The path is stored
  with its query string stripped; only the referrer *host* is kept.
- Honest reporting: rates are `null` (never 0%) when the denominator is zero,
  and stay `null` with an explicit "too early" note below 30 sessions.
"""
import datetime
import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalyticsEvent, Lead

EVENT_TYPES = ("page_view", "form_start", "submit")
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MIN_SESSIONS_FOR_RATES = 30
MAX_DAILY_DAYS = 14


def clean_path(raw: str) -> str:
    """Keep the path only - query strings can carry emails/phones."""
    value = str(raw or "").strip()
    if not value:
        return ""
    value = value.split("?", 1)[0].split("#", 1)[0]
    return value[:200]


def clean_referrer(raw: str) -> str:
    """Keep the host only - full referrers can contain search terms."""
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        host = urlparse(value if "//" in value else f"//{value}").hostname or ""
    except ValueError:
        host = ""
    return host[:200]


def record_event(db: Session, user_id: int, slug: str, body: dict) -> bool:
    """Validate and store one event. Returns False for malformed payloads."""
    if not isinstance(body, dict):
        return False
    session_id = str(body.get("session_id", "") or "")
    event = str(body.get("event", "") or "")
    if not SESSION_RE.match(session_id) or event not in EVENT_TYPES:
        return False
    db.add(
        AnalyticsEvent(
            user_id=user_id,
            slug=slug,
            session_id=session_id,
            event=event,
            path=clean_path(body.get("path", "")),
            referrer=clean_referrer(body.get("referrer", "")),
        )
    )
    return True


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def summary(
    db: Session,
    user_id: int,
    days: int = 30,
    path: str | None = None,
    landing_page: str | None = None,
) -> dict:
    """Workspace analytics, optionally narrowed to one custom page.

    ``path`` filters raw events (e.g. "/p/eid-offer"); ``landing_page`` filters
    captured leads by their ``landing_page_slug``. Passing neither keeps the
    original workspace-wide behaviour.
    """
    days = max(1, min(365, int(days)))
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(days=days)
    stmt = select(AnalyticsEvent).where(
        AnalyticsEvent.user_id == user_id, AnalyticsEvent.created_at >= since
    )
    if path:
        stmt = stmt.where(AnalyticsEvent.path == path)
    rows = db.scalars(stmt).all()

    sessions_all = {r.session_id for r in rows}
    per_event_sessions = {
        e: {r.session_id for r in rows if r.event == e} for e in EVENT_TYPES
    }
    per_event_counts = {e: sum(1 for r in rows if r.event == e) for e in EVENT_TYPES}

    page = len(per_event_sessions["page_view"])
    starts = len(per_event_sessions["form_start"])
    submits = len(per_event_sessions["submit"])

    lead_stmt = select(Lead.id).where(Lead.user_id == user_id, Lead.created_at >= since)
    if landing_page is not None:
        lead_stmt = lead_stmt.where(Lead.landing_page_slug == landing_page)
    leads_captured_count = len(db.scalars(lead_stmt).all())

    notes = []
    if not rows:
        notes.append("No analytics events recorded yet - rates are unknown, not 0%.")
    if sessions_all and len(sessions_all) < MIN_SESSIONS_FOR_RATES:
        notes.append(
            f"Only {len(sessions_all)} session(s) in this window - too early to judge rates."
        )
    if per_event_counts["submit"] > leads_captured_count:
        notes.append(
            "Client-side submit events can repeat (retries) - server-side lead captures are authoritative."
        )
    notes.append(
        "First-party, cookie-free events: ad blockers or JS-disabled visitors may be missing."
    )

    # Daily buckets (last 14 days max) for a small sparkline-style table.
    daily = []
    bucket_days = min(days, MAX_DAILY_DAYS)
    for offset in range(bucket_days - 1, -1, -1):
        day = (now - datetime.timedelta(days=offset)).date()
        day_rows = [r for r in rows if _as_date(r.created_at) == day]
        daily.append(
            {
                "date": day.isoformat(),
                "page_view": sum(1 for r in day_rows if r.event == "page_view"),
                "form_start": sum(1 for r in day_rows if r.event == "form_start"),
                "submit": sum(1 for r in day_rows if r.event == "submit"),
            }
        )

    return {
        "window_days": days,
        "events_total": len(rows),
        "sessions_total": len(sessions_all),
        "event_counts": per_event_counts,
        "funnel": {
            "page_view_sessions": page,
            "form_start_sessions": starts,
            "submit_sessions": submits,
        },
        "form_start_rate_pct": _rate(starts, page) if page >= MIN_SESSIONS_FOR_RATES else None,
        "submit_rate_pct": _rate(submits, page) if page >= MIN_SESSIONS_FOR_RATES else None,
        "leads_captured": leads_captured_count,
        "daily": daily,
        "notes": notes,
        "rates_known": page >= MIN_SESSIONS_FOR_RATES,
    }


def _as_date(value):
    if value is None:
        return None
    return value.date() if hasattr(value, "date") else value
