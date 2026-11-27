"""P7 #1: custom landing pages built from validated, text-only blocks.

Additive by design: the template-driven ``/l/<slug>`` capture page is untouched.
A custom page is a separate public URL (``/p/<slug>``) that reuses the same
consent-first capture endpoint (``POST /api/leads/capture`` with ``page_slug``).

Safety rules:
- Blocks are plain strings only. HTML is never accepted or stored, so the
  public renderer cannot inject markup (React escapes text by default).
- Every list has a hard cap and every string a length cap (see below).
- Unknown block types / unknown keys are rejected, not silently kept.
- Nothing here touches another tenant: callers pass the rows they own.
"""
import json
import re

MAX_BLOCKS = 12
MAX_PAGES = 20
MAX_FEATURES = 6
MAX_FAQS = 8
MAX_BLOCK_ITEM_TEXT = 800

# Lowercase letters/digits with inner hyphens, 3-60 chars (public URL /p/<slug>).
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])?$")
RESERVED_SLUGS = {
    "api", "admin", "login", "register", "settings", "leads", "public",
    "l", "p", "new", "edit", "app", "index",
}

BLOCK_TYPES = ("hero", "text", "features", "testimonial", "faq", "cta")


class PageValidationError(ValueError):
    """Raised for user-fixable input problems (mapped to HTTP 400)."""


def _clean(value, field: str, max_len: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise PageValidationError(f"{field} must be text.")
    text = value.strip()
    if not text:
        if required:
            raise PageValidationError(f"{field} is required.")
        return ""
    if len(text) > max_len:
        raise PageValidationError(f"{field} must be at most {max_len} characters.")
    return text


def _image_url(value, field: str) -> str:
    text = _clean(value, field, 500)
    if not text:
        return ""
    if any(ch.isspace() for ch in text):
        raise PageValidationError(f"{field} cannot contain spaces.")
    if not (text.startswith("https://") or text.startswith("/")):
        raise PageValidationError(f"{field} must be an https:// URL or a path starting with '/'.")
    return text


def _items(value, field: str, max_items: int) -> list:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise PageValidationError(f"{field} must be a list.")
    if len(value) == 0:
        raise PageValidationError(f"{field} needs at least one item.")
    if len(value) > max_items:
        raise PageValidationError(f"{field} supports at most {max_items} items.")
    for item in value:
        if not isinstance(item, dict):
            raise PageValidationError(f"{field} items must be objects.")
    return value


def _block_hero(raw: dict) -> dict:
    return {
        "type": "hero",
        "heading": _clean(raw.get("heading"), "hero heading", 120, required=True),
        "subheading": _clean(raw.get("subheading"), "hero subheading", 400),
        "cta_label": _clean(raw.get("cta_label"), "hero button label", 60),
        "image_url": _image_url(raw.get("image_url"), "hero image URL"),
    }


def _block_text(raw: dict) -> dict:
    return {
        "type": "text",
        "heading": _clean(raw.get("heading"), "text heading", 120),
        "body": _clean(raw.get("body"), "text body", 2000, required=True),
    }


def _block_features(raw: dict) -> dict:
    items = _items(raw.get("items"), "feature items", MAX_FEATURES)
    cleaned = [
        {
            "title": _clean(item.get("title"), "feature title", 80, required=True),
            "body": _clean(item.get("body"), "feature body", 300),
        }
        for item in items
    ]
    return {
        "type": "features",
        "heading": _clean(raw.get("heading"), "features heading", 120),
        "items": cleaned,
    }


def _block_testimonial(raw: dict) -> dict:
    return {
        "type": "testimonial",
        "quote": _clean(raw.get("quote"), "testimonial quote", 500, required=True),
        "author": _clean(raw.get("author"), "testimonial author", 100, required=True),
        "role": _clean(raw.get("role"), "testimonial role", 100),
    }


def _block_faq(raw: dict) -> dict:
    items = _items(raw.get("items"), "FAQ items", MAX_FAQS)
    cleaned = [
        {
            "question": _clean(item.get("question"), "FAQ question", 200, required=True),
            "answer": _clean(item.get("answer"), "FAQ answer", MAX_BLOCK_ITEM_TEXT, required=True),
        }
        for item in items
    ]
    return {
        "type": "faq",
        "heading": _clean(raw.get("heading"), "FAQ heading", 120),
        "items": cleaned,
    }


def _block_cta(raw: dict) -> dict:
    return {
        "type": "cta",
        "heading": _clean(raw.get("heading"), "call-to-action heading", 120, required=True),
        "body": _clean(raw.get("body"), "call-to-action body", 400),
        "button_label": _clean(raw.get("button_label"), "call-to-action button label", 60),
    }


_HANDLERS = {
    "hero": _block_hero,
    "text": _block_text,
    "features": _block_features,
    "testimonial": _block_testimonial,
    "faq": _block_faq,
    "cta": _block_cta,
}


def sanitize_blocks(raw) -> list[dict]:
    """Validate a whole block list and return a clean copy (unknown keys dropped)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PageValidationError("blocks must be a list.")
    if len(raw) > MAX_BLOCKS:
        raise PageValidationError(f"A page supports at most {MAX_BLOCKS} blocks.")
    out: list[dict] = []
    for index, block in enumerate(raw, start=1):
        if not isinstance(block, dict):
            raise PageValidationError(f"Block {index} must be an object.")
        block_type = str(block.get("type", "")).strip()
        handler = _HANDLERS.get(block_type)
        if handler is None:
            raise PageValidationError(
                f"Block {index} has unknown type. Allowed: {', '.join(BLOCK_TYPES)}."
            )
        out.append(handler(block))
    return out


def blocks_to_json(blocks: list[dict]) -> str:
    return json.dumps(blocks, ensure_ascii=False)


def blocks_from_json(text: str) -> list[dict]:
    """Best-effort read for stored rows: bad data renders as no blocks, never a 500."""
    try:
        return sanitize_blocks(json.loads(text or "[]"))
    except (PageValidationError, ValueError, TypeError):
        return []


def slug_error(slug: str) -> str:
    """Return a human-readable problem, or '' when the slug is acceptable."""
    if not SLUG_RE.fullmatch(slug):
        return ("slug must be 3-60 chars of lowercase letters, digits and inner hyphens "
                "(no leading/trailing hyphen).")
    if slug in RESERVED_SLUGS:
        return "That slug is reserved."
    return ""
