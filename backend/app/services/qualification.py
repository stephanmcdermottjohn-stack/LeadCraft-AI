"""BANT qualification helpers (roadmap P0 #3).

Unknown-first model: a dimension is 'known' only when a value was explicitly
recorded with a source. Completeness is honestly reported as N of 4 — never
inferred or guessed. The lifecycle suggestion (complete BANT + qualify stage →
consider nurture) mirrors the DEFAULT_NEXT_ACTION wording from the lifecycle
engine without forcing any state change.
"""
from app.models import LeadQualification

DIMENSIONS = ("budget", "authority", "need", "timing")


def empty_public() -> dict:
    """Public shape for a lead that has no row yet — every dimension unknown."""
    return {
        "dimensions": {
            d: {"value": "", "confidence": "unknown", "source": ""} for d in DIMENSIONS
        },
        "complete": 0,
        "total": 4,
        "suggestion": "",
        "updated_at": None,
    }


def serialize(q: LeadQualification) -> dict:
    dims = {}
    known = 0
    for d in DIMENSIONS:
        value = getattr(q, f"{d}_value")
        confidence = getattr(q, f"{d}_confidence")
        if confidence == "known" and value.strip():
            known += 1
        dims[d] = {
            "value": value,
            "confidence": confidence,
            "source": getattr(q, f"{d}_source"),
        }
    return {
        "dimensions": dims,
        "complete": known,
        "total": 4,
        "suggestion": _suggestion(q, known),
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
    }


def _suggestion(q: LeadQualification, known: int) -> str:
    if known == 4:
        return "BANT complete - if the lead is a good ICP fit, move it to nurture with a follow-up plan."
    if known > 0:
        remaining = [d for d in DIMENSIONS if getattr(q, f"{d}_confidence") != "known"]
        return f"Still unknown: {', '.join(remaining)} - ask on the next contact."
    return ""


def apply_patch(q: LeadQualification, updates: dict) -> None:
    """Apply manual corrections. Each dimension value is free text (<=500);
    an empty/whitespace value resets that dimension to unknown. Source is
    always 'manual' on this endpoint — AI-sourced edits arrive elsewhere."""
    for d in DIMENSIONS:
        if d not in updates:
            continue
        value = (updates[d] or "").strip()[:500]
        setattr(q, f"{d}_value", value)
        if value:
            setattr(q, f"{d}_confidence", "known")
            setattr(q, f"{d}_source", "manual")
        else:
            setattr(q, f"{d}_confidence", "unknown")
            setattr(q, f"{d}_source", "")
