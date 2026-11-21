"""Meta Lead Ads webhook processing (P4 #1).

Flow: Meta posts a `leadgen` change (only an id + page id). We store the
delivery, resolve the workspace by its configured Page id, then fetch the
full answer set from Graph API with the Page access token and create one lead
with `source='meta_lead_ad'`.

Consent: the person submitted a Lead Ad form on Meta, which carries Meta's
lead-consent language. The platform records the submission time it receives
and never invents an earlier timestamp. If the form has no phone and no email
the delivery is stored as `error` instead of creating an unusable lead.
"""
import datetime
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ClientSettings, Lead, LeadStageHistory, WebhookEvent
from app.services import webhooks

GRAPH_URL = "https://graph.facebook.com/{version}/{leadgen_id}"

# Meta form field names vary per form language; map the common ones explicitly
# and keep every unknown answer verbatim in lead metadata.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("full_name", "name", "full name", "your_name", "your name"),
    "phone": ("phone_number", "phone", "mobile", "mobile_number", "phone number"),
    "email": ("email", "email_address", "email address", "e-mail"),
    "area": ("city", "area", "location", "town", "region"),
    "notes": ("message", "notes", "comments", "service", "what_do_you_need", "what do you need?"),
}

CONSENT_NOTE = (
    "Lead came from a Meta Lead Ad form (the person submitted their details on "
    "Meta). Consent timestamp is the webhook delivery time, recorded server-side."
)


class MetaError(Exception):
    pass


def parse_leadgen_entries(payload: dict) -> list[dict]:
    """Flatten a `page` webhook body into one dict per leadgen change."""
    entries: list[dict] = []
    for entry in payload.get("entry") or []:
        entry_page_id = str(entry.get("id") or "")
        for change in entry.get("changes") or []:
            if change.get("field") != "leadgen":
                continue
            value = change.get("value") or {}
            leadgen_id = str(value.get("leadgen_id") or "").strip()
            if not leadgen_id:
                continue
            entries.append(
                {
                    "leadgen_id": leadgen_id,
                    "page_id": str(value.get("page_id") or entry_page_id),
                    "form_id": str(value.get("form_id") or ""),
                    "ad_id": str(value.get("ad_id") or ""),
                    "created_time": value.get("created_time"),
                }
            )
    return entries


def event_key(entry: dict) -> str:
    return f"meta_leadgen:{entry['leadgen_id']}"[:200]


def fetch_lead_fields(leadgen_id: str, access_token: str, api_version: str) -> list[dict]:
    """Graph API call. Isolated so tests can monkeypatch it (no network)."""
    if not access_token:
        raise MetaError("META_PAGE_ACCESS_TOKEN is not configured.")
    url = GRAPH_URL.format(version=api_version or "v21.0", leadgen_id=leadgen_id)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params={"access_token": access_token})
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:  # includes timeouts / non-2xx
        raise MetaError(f"Graph API request failed: {exc}") from exc
    except ValueError as exc:
        raise MetaError("Graph API returned a non-JSON body.") from exc
    fields = data.get("field_data")
    if not isinstance(fields, list):
        raise MetaError("Graph API response has no field_data.")
    return fields


def map_fields(field_data: list[dict]) -> dict:
    """Map Meta answers onto lead columns + keep the full answer set."""
    values: dict[str, str] = {}
    for item in field_data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("name") or "").strip().lower()
        raw = item.get("values")
        if isinstance(raw, list):
            text = ", ".join(str(v).strip() for v in raw if str(v).strip())
        else:
            text = str(raw or "").strip()
        if key and text:
            values[key] = text[:1000]

    mapped = {"name": "", "phone": "", "email": "", "area": "", "notes": ""}
    for column, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if values.get(alias):
                mapped[column] = values[alias]
                break

    consumed = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
    extras = {k: v for k, v in values.items() if k not in consumed}
    mapped["extras"] = extras
    mapped["answers"] = values
    return mapped


def _find_workspace(db: Session, page_id: str) -> ClientSettings | None:
    if not page_id:
        return None
    return db.scalar(select(ClientSettings).where(ClientSettings.meta_page_id == page_id))


def create_lead(
    db: Session, user_id: int, entry: dict, mapped: dict, received_at: datetime.datetime
) -> Lead:
    metadata = {
        "integration": "meta_lead_ad",
        "leadgen_id": entry.get("leadgen_id", ""),
        "page_id": entry.get("page_id", ""),
        "form_id": entry.get("form_id", ""),
        "ad_id": entry.get("ad_id", ""),
        "answers": mapped["answers"],
        "extra_answers": mapped["extras"],
        "consent_note": CONSENT_NOTE,
    }
    lead = Lead(
        user_id=user_id,
        source="meta_lead_ad",
        name=mapped["name"] or "Meta lead",
        phone=mapped["phone"],
        email=mapped["email"].lower(),
        area=mapped["area"],
        intent_notes=mapped["notes"],
        consent_timestamp=received_at,
        score=0,
        status="new",
        lifecycle_stage="capture",
        utm_source="meta",
        metadata_json=json.dumps(metadata),
        created_at=received_at,
    )
    db.add(lead)
    db.flush()
    db.add(
        LeadStageHistory(
            lead_id=lead.id,
            user_id=user_id,
            from_stage="",
            to_stage="capture",
            note="captured via Meta Lead Ads webhook",
        )
    )
    return lead


def process_event(db: Session, event: WebhookEvent, config: Settings) -> WebhookEvent:
    """Route + fetch + create one lead. Caller commits."""
    try:
        entry = json.loads(event.payload_json or "{}")
    except ValueError:
        return webhooks.mark(db, event, "error", error="Stored payload is not valid JSON.")

    page_id = str(entry.get("page_id") or "")
    settings_row = _find_workspace(db, page_id)
    if settings_row is None:
        return webhooks.mark(
            db,
            event,
            "unrouted",
            error=f"No workspace is configured for Meta page id '{page_id or 'unknown'}'.",
        )
    if event.user_id is None:
        event.user_id = settings_row.user_id

    if not config.meta_page_access_token:
        return webhooks.mark(
            db,
            event,
            "pending_credentials",
            error="META_PAGE_ACCESS_TOKEN is not configured, so the lead answers were not fetched.",
        )

    try:
        field_data = fetch_lead_fields(
            entry.get("leadgen_id", ""), config.meta_page_access_token, config.meta_api_version
        )
        mapped = map_fields(field_data)
        if not mapped["phone"] and not mapped["email"]:
            return webhooks.mark(
                db, event, "error", error="Form answers contain neither a phone number nor an email."
            )
        lead = create_lead(
            db,
            settings_row.user_id,
            entry,
            mapped,
            datetime.datetime.now(datetime.timezone.utc),
        )
    except MetaError as exc:
        return webhooks.mark(db, event, "error", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - the event log must capture anything
        return webhooks.mark(db, event, "error", error=f"Unexpected error: {exc}")

    return webhooks.mark(db, event, "processed", lead_id=lead.id)
