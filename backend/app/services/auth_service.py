"""Authentication service (Phase 1 skeleton).

Design (deliberately dependency-light):
- Passwords: PBKDF2-HMAC-SHA256, 390k iterations (OWASP 2023 rec), 16-byte
  random salt per user. Hash format: pbkdf2_sha256$iterations$salt_hex$hash_hex.
- Tokens: stateless HMAC-signed `base64url(payload).base64url(sig)` with
  SECRET_KEY from env. MVP-simple; upgrade to Supabase Auth or short-lived
  JWTs before production traffic. Payload carries user id + issued-at so
  tokens can be revoked by rotating the secret or by a later allowlist.
- No third-party dependency required for this skeleton.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def _secret_key() -> str:
    return os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")


def _sign(payload_b64: str) -> str:
    return hmac.new(_secret_key().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: int, ttl_seconds: int = 7 * 24 * 3600) -> str:
    payload = {"uid": user_id, "iat": int(time.time()), "exp": int(time.time()) + ttl_seconds}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str) -> int | None:
    """Return user_id when the token is valid and unexpired, else None."""
    try:
        payload_b64, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(payload_b64), sig):
        return None
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    uid = payload.get("uid")
    return int(uid) if isinstance(uid, int) else None
