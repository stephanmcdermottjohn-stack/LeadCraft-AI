"""Login / registration brute-force throttling (security pass).

Why DB-backed: the API runs as Vercel serverless functions, so an in-process
counter would reset on every cold start. Each counter is a single row keyed by
a SHA-256 hash of its scope, so no plaintext email address or IP address is
persisted.

Policy (conservative, all local - zero external cost):

- **login per email + IP:** 5 failures in 15 minutes -> locked 15 minutes.
  Keying on both means one attacker cannot lock a real user out from another
  IP, and spraying many emails from one IP is caught by the IP counter.
- **login per IP:** 30 failures in 15 minutes -> locked 15 minutes.
- **register per IP:** 5 attempts in 1 hour -> locked 1 hour.

A locked caller gets `429` with `Retry-After`. Successful login clears the
email+IP counter but deliberately **not** the pure IP counter (otherwise one
valid account could reset an IP-wide attack counter). Unknown emails are
throttled exactly like real ones.
"""
import datetime
import hashlib
import secrets

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import AuthThrottle

LOGIN_MAX_FAILURES = 5
IP_MAX_FAILURES = 30
REGISTER_MAX_ATTEMPTS = 5

LOGIN_WINDOW = datetime.timedelta(minutes=15)
LOGIN_LOCK = datetime.timedelta(minutes=15)
IP_WINDOW = datetime.timedelta(minutes=15)
IP_LOCK = datetime.timedelta(minutes=15)
REGISTER_WINDOW = datetime.timedelta(hours=1)
REGISTER_LOCK = datetime.timedelta(hours=1)

# Rows whose window has long expired are useless; prune them occasionally.
STALE_AFTER = datetime.timedelta(days=1)
CLEANUP_ONE_IN = 20


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(value: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite returns naive datetimes; treat them as UTC for comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def client_ip(request) -> str:
    """Best-effort client IP behind Vercel / reverse proxies."""
    headers = request.headers
    for name in ("x-real-ip", "x-vercel-forwarded-for", "x-forwarded-for"):
        raw = headers.get(name)
        if raw:
            # Proxies append; the left-most value is the original client.
            first = raw.split(",")[0].strip()
            if first:
                return first[:64]
    client = getattr(request, "client", None)
    return (client.host if client and client.host else "unknown")[:64]


def _login_email_key(email: str, ip: str) -> str:
    return _hash(f"login|{email.strip().lower()}|{ip}")


def _login_ip_key(ip: str) -> str:
    return _hash(f"login-ip|{ip}")


def _register_ip_key(ip: str) -> str:
    return _hash(f"register|{ip}")


def retry_after(db: Session, key_hash: str) -> int | None:
    """Seconds until the lock expires, or None when not locked."""
    row = db.get(AuthThrottle, key_hash)
    if row is None:
        return None
    locked_until = _aware(row.locked_until)
    if locked_until is None:
        return None
    remaining = (locked_until - _now()).total_seconds()
    return max(1, int(remaining + 0.999)) if remaining > 0 else None


def _bump(
    db: Session,
    key_hash: str,
    *,
    limit: int,
    window: datetime.timedelta,
    lock: datetime.timedelta,
) -> None:
    now = _now()
    row = db.get(AuthThrottle, key_hash)
    if row is None:
        row = AuthThrottle(key_hash=key_hash, failures=0, window_start=now)
        db.add(row)
    window_start = _aware(row.window_start)
    if window_start is None or now - window_start > window:
        row.failures = 1
        row.window_start = now
        row.locked_until = None
    else:
        row.failures = int(row.failures or 0) + 1
    if row.failures >= limit:
        row.locked_until = now + lock
    row.updated_at = now
    db.flush()


def _cleanup(db: Session) -> None:
    """Occasionally prune counters that have been idle for a day."""
    if secrets.randbelow(CLEANUP_ONE_IN) != 0:
        return
    cutoff = _now() - STALE_AFTER
    db.execute(delete(AuthThrottle).where(AuthThrottle.updated_at < cutoff))


def login_retry_after(db: Session, email: str, ip: str) -> int | None:
    """Worst case of the email+IP and IP-wide locks."""
    values = [
        retry_after(db, _login_email_key(email, ip)),
        retry_after(db, _login_ip_key(ip)),
    ]
    waits = [v for v in values if v]
    return max(waits) if waits else None


def record_login_failure(db: Session, email: str, ip: str) -> None:
    _bump(
        db,
        _login_email_key(email, ip),
        limit=LOGIN_MAX_FAILURES,
        window=LOGIN_WINDOW,
        lock=LOGIN_LOCK,
    )
    _bump(db, _login_ip_key(ip), limit=IP_MAX_FAILURES, window=IP_WINDOW, lock=IP_LOCK)
    _cleanup(db)
    db.commit()


def clear_login(db: Session, email: str, ip: str) -> None:
    """Successful login: forget this email+IP pair. The IP-wide counter stays
    so a single valid account cannot erase an ongoing spray from that IP."""
    db.execute(delete(AuthThrottle).where(AuthThrottle.key_hash == _login_email_key(email, ip)))
    db.commit()


def register_retry_after(db: Session, ip: str) -> int | None:
    return retry_after(db, _register_ip_key(ip))


def record_register_attempt(db: Session, ip: str) -> None:
    _bump(
        db,
        _register_ip_key(ip),
        limit=REGISTER_MAX_ATTEMPTS,
        window=REGISTER_WINDOW,
        lock=REGISTER_LOCK,
    )
    _cleanup(db)
    db.commit()
