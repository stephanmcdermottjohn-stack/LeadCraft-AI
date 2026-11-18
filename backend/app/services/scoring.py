"""Engagement scoring + grade snapshotting (roadmap P0 #5).

Score ≠ grade, by design:
- score: a heuristic engagement number built from consent + activity signals
  with user-configurable weights. Always labeled "heuristic — not a
  calibrated probability".
- grade: the ICP-fit snapshot (A-D) from the fit module; unknown ICP signal
  yields "" rather than a guess.

Snapshots are append-only: changing weights or editing an ICP never rewrites
a historical row. The conversion-feedback function is the recalibration hook
—it reports outcomes honestly and changes nothing by itself.
"""
import json

from app.services import icp as icp_service
from app.services.qualification import DIMENSIONS

DEFAULT_WEIGHTS: dict[str, int] = {
    "consent_base": 10,       # every consented lead starts here
    "per_note": 3,            # per follow-up note (first 5 counted)
    "per_bant_known": 5,      # per known BANT dimension (0-4)
    "budget_stated": 10,      # lead explicitly gave a budget figure
    "stage_qualify": 5,
    "stage_nurture": 10,
    "stage_convert": 15,
    "stage_retain": 15,
    "stage_reactivate": 5,
    "stage_capture": 0,
}

STAGE_WEIGHT_KEYS = {
    "capture": "stage_capture",
    "qualify": "stage_qualify",
    "nurture": "stage_nurture",
    "convert": "stage_convert",
    "retain": "stage_retain",
    "reactivate": "stage_reactivate",
}

MAX_NOTES_COUNTED = 5

SCORE_LABEL = "heuristic engagement score — not a calibrated probability"


def sanitize_weights(raw: dict | None) -> dict[str, int]:
    """Keep only known keys with sane int values (0..100); merge with defaults."""
    weights = dict(DEFAULT_WEIGHTS)
    if not isinstance(raw, dict):
        return weights
    for key, value in raw.items():
        if key in DEFAULT_WEIGHTS and isinstance(value, int) and not isinstance(value, bool):
            weights[key] = max(0, min(100, value))
    return weights


def effective_weights(settings_row) -> dict[str, int]:
    try:
        raw = json.loads(getattr(settings_row, "scoring_weights_json", "") or "{}")
        if not isinstance(raw, dict):
            raw = {}
    except ValueError:
        raw = {}
    return sanitize_weights(raw)


def compute(stage: str, notes_count: int, bant_known: int, budget_stated: bool, weights: dict) -> dict:
    """Pure computation. Returns {score, label, factors} — transparent per-signal breakdown."""
    stage_key = STAGE_WEIGHT_KEYS.get(stage, "stage_capture")
    notes_capped = min(max(notes_count, 0), MAX_NOTES_COUNTED)
    bant_known = max(0, min(bant_known, len(DIMENSIONS)))
    factors = [
        {
            "signal": "consent",
            "points": weights["consent_base"],
            "weight": weights["consent_base"],
            "detail": "Consented lead - base points for a usable, opt-in contact.",
        },
        {
            "signal": "notes",
            "points": notes_capped * weights["per_note"],
            "weight": MAX_NOTES_COUNTED * weights["per_note"],
            "detail": f"{notes_count} follow-up note(s) ({notes_capped} counted, max {MAX_NOTES_COUNTED}).",
        },
        {
            "signal": "bant",
            "points": bant_known * weights["per_bant_known"],
            "weight": len(DIMENSIONS) * weights["per_bant_known"],
            "detail": f"{bant_known}/4 BANT dimensions known (unknown dims earn nothing but are not penalized).",
        },
        {
            "signal": "budget",
            "points": weights["budget_stated"] if budget_stated else 0,
            "weight": weights["budget_stated"],
            "detail": "Lead stated a budget figure." if budget_stated else "No budget stated yet.",
        },
        {
            "signal": "stage",
            "points": weights[stage_key],
            "weight": max(weights.values()),
            "detail": f"Lifecycle stage: {stage}.",
        },
    ]
    return {
        "score": sum(f["points"] for f in factors),
        "label": SCORE_LABEL,
        "factors": factors,
        "weights_used": weights,
    }


def parse_reason(reason_json: str) -> dict:
    try:
        parsed = json.loads(reason_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def conversion_feedback(rows: list[dict]) -> dict:
    """Recalibration hook: compare converted vs not-converted snapshot scores.

    Rows are {score, converted} dicts from the latest snapshot per lead.
    Honest output: below MIN_CONVERSIONS no recalibration is suggested at all.
    """
    MIN_CONVERSIONS = 5
    converted = [r["score"] for r in rows if r.get("converted")]
    others = [r["score"] for r in rows if not r.get("converted")]
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else None  # noqa: E731
    return {
        "converted_count": len(converted),
        "avg_score_converted": avg(converted),
        "avg_score_other": avg(others),
        "ready_for_recalibration": len(converted) >= MIN_CONVERSIONS,
        "note": (
            f"Needs at least {MIN_CONVERSIONS} converted leads with score snapshots before any recalibration is suggested."
            if len(converted) < MIN_CONVERSIONS
            else "Enough conversion data exists to review weights manually - recalibration stays a human decision."
        ),
    }


def grade_for_lead(icp_profile, lead: dict) -> str:
    """ICP-fit grade snapshot ("" when no profile or no evaluable signal)."""
    if icp_profile is None:
        return ""
    fit = icp_service.match_lead(icp_profile, lead)
    return fit.get("grade", "")
