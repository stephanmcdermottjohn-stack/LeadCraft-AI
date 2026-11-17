"""Lead lifecycle engine (roadmap P0 #1).

Standard stages: capture -> qualify -> nurture -> convert -> retain ->
reactivate. Kept as a fixed constant for P0 so standard reporting stays
stable; custom per-organization stage configs slot in later via
`lifecycle_config_json` on client settings without changing these codes.

CRM `status` (new/contacted/converted/archived) and `lifecycle_stage` are
independent concepts: status is the sales team's working funnel, the stage is
the marketing lifecycle. One bridge exists: setting status=converted
auto-advances the stage to `convert` (logged in stage history).
"""
import datetime

STAGES = ("capture", "qualify", "nurture", "convert", "retain", "reactivate")

# Suggested next action per stage — a starting recommendation the owner can
# overwrite; never treated as an automated task.
DEFAULT_NEXT_ACTION = {
    "capture": "Review and move to qualify (run ICP fit + BANT).",
    "qualify": "Complete BANT; if fit, move to nurture with a follow-up plan.",
    "nurture": "Send consented follow-up; check response before converting.",
    "convert": "Confirm outcome; on win, move to retain with an onboarding touchpoint.",
    "retain": "Schedule a retention check-in (feedback, upsell where legitimate).",
    "reactivate": "Re-engage with a consent-based offer; update qualification.",
}


def is_valid_stage(value: str) -> bool:
    return value in STAGES


def default_next_action(stage: str) -> str:
    return DEFAULT_NEXT_ACTION.get(stage, "")


def stage_entry(from_stage: str, to_stage: str, note: str) -> dict:
    return {
        "from_stage": from_stage,
        "to_stage": to_stage,
        "note": (note or "").strip()[:500],
        "changed_at": datetime.datetime.now(datetime.timezone.utc),
    }
