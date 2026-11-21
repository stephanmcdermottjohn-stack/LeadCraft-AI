"""WhatsApp Cloud API inbound webhook (P4 #2).

Inbound messages only - no auto-reply, no outbound sends. Delivery status
callbacks are acknowledged and ignored (the platform does not track delivery).

Same handshake/signature rules as the Meta endpoint: 503 while unconfigured,
403 on a bad signature, 200 after a stored delivery.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import webhooks, whatsapp

router = APIRouter(prefix="/api/webhooks/whatsapp")


@router.get("")
def verify(request: Request) -> PlainTextResponse:
    config = get_settings()
    params = request.query_params
    if not config.meta_verify_token:
        raise HTTPException(
            status_code=503,
            detail="WhatsApp webhook is not configured: set META_VERIFY_TOKEN and the App Secret first.",
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
            detail="WhatsApp webhook is not configured: set META_APP_SECRET to enable signed deliveries.",
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

    received = processed = duplicates = unrouted = errors = 0
    for message in whatsapp.parse_messages(payload):
        event, created = webhooks.store_event(
            db,
            source="whatsapp",
            event_key=whatsapp.event_key(message),
            payload=message,
            signature_valid=signed,
        )
        if not created:
            duplicates += 1
            continue
        received += 1
        whatsapp.process_event(db, event)
        db.commit()
        if event.status == "processed":
            processed += 1
        elif event.status == "unrouted":
            unrouted += 1
        elif event.status == "error":
            errors += 1

    return {
        "status": "ok",
        "received": received,
        "processed": processed,
        "duplicates": duplicates,
        "unrouted": unrouted,
        "errors": errors,
        "note": "Inbound only - the platform never auto-replies.",
    }
