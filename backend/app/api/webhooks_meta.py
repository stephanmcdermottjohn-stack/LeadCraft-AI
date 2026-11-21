"""Meta Lead Ads webhook endpoint (P4 #1).

- `GET /api/webhooks/meta` — Meta's subscription handshake. 503 while
  `META_VERIFY_TOKEN` is unset (webhook is off, honestly), 403 on a wrong
  token, otherwise echoes `hub.challenge`.
- `POST /api/webhooks/meta` — delivery. 503 while `META_APP_SECRET` is unset;
  every delivery must carry a valid `X-Hub-Signature-256` (403 otherwise).
  Accepted deliveries always answer 200 after being stored, because Meta
  retries non-2xx responses and our event log + manual retry already covers
  transient Graph failures.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import meta_leadgen, webhooks

router = APIRouter(prefix="/api/webhooks/meta")


@router.get("")
def verify(request: Request) -> PlainTextResponse:
    config = get_settings()
    params = request.query_params
    if not config.meta_verify_token:
        raise HTTPException(
            status_code=503,
            detail="Meta webhook is not configured: set META_VERIFY_TOKEN and the App Secret first.",
        )
    if params.get("hub.mode") != "subscribe":
        raise HTTPException(status_code=400, detail="hub.mode must be 'subscribe'.")
    if params.get("hub.verify_token") != config.meta_verify_token:
        raise HTTPException(status_code=403, detail="Verification token mismatch.")
    return PlainTextResponse(params.get("hub.challenge", ""))


@router.post("")
async def receive(request: Request, db: Session = Depends(get_db)) -> dict:
    config = get_settings()
    raw = await request.body()
    if not config.meta_app_secret:
        raise HTTPException(
            status_code=503,
            detail="Meta webhook is not configured: set META_APP_SECRET to enable signed deliveries.",
        )
    signed = webhooks.signature_valid(
        config.meta_app_secret, raw, request.headers.get("x-hub-signature-256")
    )
    if not signed:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Hub-Signature-256.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Body must be valid JSON.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    received = processed = duplicates = unrouted = pending = errors = 0
    for entry in meta_leadgen.parse_leadgen_entries(payload):
        event, created = webhooks.store_event(
            db,
            source="meta_leadgen",
            event_key=meta_leadgen.event_key(entry),
            payload=entry,
            signature_valid=signed,
        )
        if not created:
            duplicates += 1
            continue
        received += 1
        meta_leadgen.process_event(db, event, config)
        db.commit()
        if event.status == "processed":
            processed += 1
        elif event.status == "unrouted":
            unrouted += 1
        elif event.status == "pending_credentials":
            pending += 1
        elif event.status == "error":
            errors += 1

    return {
        "status": "ok",
        "received": received,
        "processed": processed,
        "duplicates": duplicates,
        "unrouted": unrouted,
        "pending_credentials": pending,
        "errors": errors,
    }
