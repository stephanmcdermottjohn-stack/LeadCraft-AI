"""Duplicate lead detection & safe merge (P6 #1 v1).

Detection is **exact on normalized contact values only** — no fuzzy name
matching, no ML, no external service:

- phone: digits only, `00` stripped, `+92`/`92` collapsed, compared on the
  last 10 digits (so `0300 1234567`, `+92 300 1234567` and `3001234567` match)
- email: trimmed and lowercased

Merging keeps one primary lead and moves every child record onto it before the
duplicate rows are deleted. Rules are deliberately conservative and honest:

- the **primary wins** on status, lifecycle stage, source and any field it
  already has; empty fields are filled from duplicates and reported
- deal outcomes are **never summed**: if the primary already has one, the
  duplicate's outcome is kept in the merge summary as a conflict, not revenue
- qualification dimensions use the same "unknown is not zero" rule: a known
  duplicate value fills an unknown primary dimension, never overwrites a known one
- conversations on the same channel are merged (messages preserved); nurture
  enrollments in a campaign the primary already has are reported, not duplicated
- timeline/notes/stage history/score history/appointments/reviews/webhook links
  are reassigned to the primary
- one append-only `LeadActivity` records the merge on the primary timeline and
  one audit-log row records who merged what (ids/counts only, no contact data)

Every query is tenant-scoped by `user_id`; another workspace's lead returns 404.
"""
import datetime
import json

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    Conversation,
    DealOutcome,
    Lead,
    LeadActivity,
    LeadNote,
    LeadQualification,
    LeadScoreHistory,
    LeadStageHistory,
    Message,
    NurtureEnrollment,
    ReviewRequest,
    User,
    WebhookEvent,
)
from app.services import audit as audit_svc

SCAN_LIMIT = 5000
GROUP_LIMIT = 200
MERGE_LIMIT = 10
PHONE_MIN_DIGITS = 7
CONFLICT_LIMIT = 20

QUALIFICATION_DIMS = ("budget", "authority", "need", "timing")

# Fields that only get filled when the primary is empty (primary never loses data).
FILL_FIELDS = (
    "name",
    "phone",
    "email",
    "area",
    "assigned_to",
    "next_action",
    "next_action_at",
    "campaign",
    "utm_source",
    "utm_medium",
    "utm_content",
    "utm_term",
    "landing_variant",
    "grade",
)

SIMPLE_CHILD_TABLES = (
    LeadNote,
    LeadStageHistory,
    LeadActivity,
    LeadScoreHistory,
    Appointment,
    ReviewRequest,
)

DETECTION_NOTES = [
    "Phone matches use digits only, +92/0 collapsed, compared on the last 10 digits.",
    "Email matches are exact after trimming and lowercasing.",
    "Names are never fuzzy-matched - detection never guesses.",
    f"Up to {SCAN_LIMIT:,} leads are scanned; truncation is reported honestly.",
]


def normalize_phone(value: str | None) -> str:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("92") and len(digits) >= 11:
        digits = "0" + digits[2:]
    if len(digits) > 10:
        digits = digits[-10:]
    return digits if len(digits) >= PHONE_MIN_DIGITS else ""


def normalize_email(value: str | None) -> str:
    email = (value or "").strip().lower()
    if len(email) < 5 or "@" not in email or email.startswith("@") or email.endswith("@"):
        return ""
    return email


def _keys(lead: Lead) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    phone = normalize_phone(lead.phone)
    email = normalize_email(lead.email)
    if phone:
        keys.append(("phone", phone))
    if email:
        keys.append(("email", email))
    return keys


def _utc(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=datetime.timezone.utc) if value.tzinfo is None else value


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _row(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "status": lead.status,
        "lifecycle_stage": lead.lifecycle_stage,
        "source": lead.source,
        "campaign": lead.campaign,
        "score": lead.score,
        "grade": lead.grade,
        "created_at": _iso(lead.created_at),
        "consent_timestamp": _iso(lead.consent_timestamp),
    }


def _tenant_leads(db: Session, user_id: int, limit: int = SCAN_LIMIT) -> tuple[list[Lead], bool]:
    rows = list(
        db.scalars(
            select(Lead)
            .where(Lead.user_id == user_id)
            .order_by(Lead.created_at.asc(), Lead.id.asc())
            .limit(limit + 1)
        ).all()
    )
    return rows[:limit], len(rows) > limit


def find_groups(db: Session, user: User, limit: int = GROUP_LIMIT) -> dict:
    leads, truncated = _tenant_leads(db, user.id)

    parent = {lead.id: lead.id for lead in leads}

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_key: dict[tuple[str, str], list[Lead]] = {}
    for lead in leads:
        for key in _keys(lead):
            by_key.setdefault(key, []).append(lead)

    group_kinds: dict[int, set[str]] = {}
    for (kind, _value), members in by_key.items():
        if len(members) < 2:
            continue
        first = members[0].id
        for member in members[1:]:
            union(first, member.id)
        group_kinds.setdefault(find(first), set()).add(kind)

    components: dict[int, list[Lead]] = {}
    for lead in leads:
        components.setdefault(find(lead.id), []).append(lead)

    groups = []
    for root, members in components.items():
        if len(members) < 2:
            continue
        kinds = sorted(group_kinds.get(root, set()))
        ordered = sorted(members, key=lambda l: (_utc(l.created_at), l.id))
        groups.append({"key": f"group-{root}", "matched_on": kinds, "leads": [_row(l) for l in ordered]})

    groups.sort(key=lambda g: (-len(g["leads"]), g["leads"][0]["id"]))
    return {
        "groups": groups[:limit],
        "groups_total": len(groups),
        "scanned": len(leads),
        "truncated": truncated,
        "notes": DETECTION_NOTES,
    }


def duplicates_for_lead(db: Session, user: User, lead_id: int) -> dict | None:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.user_id != user.id:
        return None

    leads, truncated = _tenant_leads(db, user.id)
    phone = normalize_phone(lead.phone)
    email = normalize_email(lead.email)

    candidates = []
    for other in leads:
        if other.id == lead.id:
            continue
        matched: list[str] = []
        conflicts: list[str] = []
        other_phone = normalize_phone(other.phone)
        other_email = normalize_email(other.email)
        if phone and other_phone == phone:
            matched.append("phone")
        elif phone and other_phone and other_phone != phone:
            conflicts.append("phone differs")
        if email and other_email == email:
            matched.append("email")
        elif email and other_email and other_email != email:
            conflicts.append("email differs")
        if matched:
            row = _row(other)
            row["matched_on"] = matched
            row["conflicts"] = conflicts
            candidates.append(row)

    candidates.sort(key=lambda r: (r["created_at"] or "", r["id"]))
    return {
        "lead": _row(lead),
        "candidates": candidates,
        "scanned": len(leads),
        "truncated": truncated,
        "notes": DETECTION_NOTES,
    }


# --- merge helpers ---------------------------------------------------------


def _count(db: Session, model, ids: list[int]) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(model.lead_id.in_(ids))) or 0)


def _count_messages(db: Session, conversation_ids: list[int]) -> int:
    if not conversation_ids:
        return 0
    return int(
        db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id.in_(conversation_ids))
        )
        or 0
    )


def _q_plan(base: LeadQualification | None, others: list[LeadQualification]) -> tuple[list[str], list[str]]:
    """Which unknown dimensions would be filled, and which known ones conflict."""
    filled: list[str] = []
    conflicts: list[str] = []
    for dim in QUALIFICATION_DIMS:
        base_conf = getattr(base, f"{dim}_confidence") if base is not None else "unknown"
        base_value = (getattr(base, f"{dim}_value") if base is not None else "") or ""
        if base_conf != "known":
            if any(getattr(q, f"{dim}_confidence") == "known" for q in others):
                filled.append(f"qualification.{dim}")
        else:
            for q in others:
                if getattr(q, f"{dim}_confidence") == "known" and (
                    (getattr(q, f"{dim}_value") or "").strip() != base_value.strip()
                ):
                    conflicts.append(f"qualification.{dim} kept primary")
                    break
    return filled, conflicts


def _apply_q(base: LeadQualification, others: list[LeadQualification], primary_id: int) -> tuple[list[str], list[str]]:
    filled, conflicts = _q_plan(base, others)
    for dim in QUALIFICATION_DIMS:
        if getattr(base, f"{dim}_confidence") == "known":
            continue
        for q in others:
            if getattr(q, f"{dim}_confidence") == "known":
                for suffix in ("value", "confidence", "source"):
                    setattr(base, f"{dim}_{suffix}", getattr(q, f"{dim}_{suffix}"))
                break
    base.lead_id = primary_id
    base.updated_at = datetime.datetime.now(datetime.timezone.utc)
    return filled, conflicts


def _preview(db: Session, primary: Lead, dups: list[Lead]) -> dict:
    ids = [d.id for d in dups]
    moved = {
        "notes": _count(db, LeadNote, ids),
        "stage_history": _count(db, LeadStageHistory, ids),
        "activities": _count(db, LeadActivity, ids),
        "score_history": _count(db, LeadScoreHistory, ids),
        "appointments": _count(db, Appointment, ids),
        "review_requests": _count(db, ReviewRequest, ids),
        "webhook_events": _count(db, WebhookEvent, ids),
    }

    primary_q = db.scalar(select(LeadQualification).where(LeadQualification.lead_id == primary.id))
    dup_qs = list(
        db.scalars(
            select(LeadQualification)
            .where(LeadQualification.lead_id.in_(ids))
            .order_by(LeadQualification.id.asc())
        ).all()
    )
    q_base = primary_q or (dup_qs[0] if dup_qs else None)
    q_others = dup_qs if primary_q is not None else dup_qs[1:]
    fills, conflicts = _q_plan(q_base, q_others)
    moved["qualifications"] = 1 if (primary_q is None and dup_qs) else 0

    primary_deal = db.scalar(select(DealOutcome).where(DealOutcome.lead_id == primary.id))
    dup_deals = list(
        db.scalars(
            select(DealOutcome)
            .where(DealOutcome.lead_id.in_(ids))
            .order_by(DealOutcome.id.asc())
        ).all()
    )
    moved["deal_outcomes"] = 1 if (primary_deal is None and dup_deals) else 0
    if primary_deal is not None:
        for deal in dup_deals:
            conflicts.append(
                f"deal outcome kept on primary (lead #{deal.lead_id}: {deal.status} {deal.amount:g} {deal.currency} not summed)"
            )

    primary_campaigns = set(
        db.scalars(select(NurtureEnrollment.campaign_id).where(NurtureEnrollment.lead_id == primary.id)).all()
    )
    moved["nurture_enrollments"] = 0
    for enrollment in db.scalars(select(NurtureEnrollment).where(NurtureEnrollment.lead_id.in_(ids))).all():
        if enrollment.campaign_id in primary_campaigns:
            conflicts.append(
                f"nurture enrollment in campaign #{enrollment.campaign_id} kept on primary"
            )
        else:
            moved["nurture_enrollments"] += 1
            primary_campaigns.add(enrollment.campaign_id)

    primary_channels = set(
        db.scalars(select(Conversation.channel).where(Conversation.lead_id == primary.id)).all()
    )
    dup_convs = list(db.scalars(select(Conversation).where(Conversation.lead_id.in_(ids))).all())
    moved["conversations"] = 0
    moved["conversations_merged"] = 0
    moved["messages"] = _count_messages(db, [c.id for c in dup_convs])
    for conv in dup_convs:
        if conv.channel in primary_channels:
            moved["conversations_merged"] += 1
        else:
            moved["conversations"] += 1
            primary_channels.add(conv.channel)

    moved["referred_leads"] = int(
        db.scalar(select(func.count()).select_from(Lead).where(Lead.referred_by_lead_id.in_(ids))) or 0
    )

    field_fills, field_conflicts = _field_plan(primary, dups)
    fills = fills + [item for item in field_fills if item not in fills]
    conflicts = conflicts + field_conflicts

    return {
        "primary": _row(primary),
        "duplicates": [_row(d) for d in dups],
        "moved": moved,
        "fields_filled": fills,
        "conflicts": conflicts,
    }


def _field_plan(primary: Lead, dups: list[Lead]) -> tuple[list[str], list[str]]:
    """Which empty primary fields would be filled, and which values conflict."""
    filled: list[str] = []
    conflicts: list[str] = []

    for field in FILL_FIELDS:
        if getattr(primary, field):
            continue
        if any(getattr(dup, field) for dup in dups):
            filled.append(field)

    seen_notes = (primary.intent_notes or "").strip()
    for dup in dups:
        extra = (dup.intent_notes or "").strip()
        if extra and extra not in seen_notes:
            filled.append(f"intent_notes (from #{dup.id})")
            seen_notes = (seen_notes + "\n" + extra) if seen_notes else extra

    try:
        metadata = json.loads(primary.metadata_json or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
    except (ValueError, TypeError):
        metadata = {}
    for dup in dups:
        try:
            other = json.loads(dup.metadata_json or "{}")
        except (ValueError, TypeError):
            other = {}
        if not isinstance(other, dict):
            continue
        for key, value in other.items():
            if key not in metadata or not str(metadata.get(key, "")).strip():
                metadata[key] = value
                filled.append(f"metadata.{key}")

    for dup in dups:
        if dup.status != primary.status:
            conflicts.append(f"status kept '{primary.status}' (lead #{dup.id}: '{dup.status}')")
        if dup.lifecycle_stage != primary.lifecycle_stage:
            conflicts.append(
                f"stage kept '{primary.lifecycle_stage}' (lead #{dup.id}: '{dup.lifecycle_stage}')"
            )
        if dup.source != primary.source:
            conflicts.append(f"source kept '{primary.source}' (lead #{dup.id}: '{dup.source}')")
        if primary.referral_code and dup.referral_code and dup.referral_code != primary.referral_code:
            conflicts.append(f"referral code kept primary (lead #{dup.id} code deactivated)")

    if not primary.referral_code and any(dup.referral_code for dup in dups):
        filled.append("referral_code")

    return filled, conflicts


def _fill_primary(primary: Lead, dups: list[Lead]) -> tuple[list[str], list[str]]:
    planned_fills, planned_conflicts = _field_plan(primary, dups)

    for field in FILL_FIELDS:
        if getattr(primary, field):
            continue
        for dup in dups:
            value = getattr(dup, field)
            if value:
                setattr(primary, field, value)
                break

    # Free-text intent notes: keep both, clearly labelled. Never silently drop.
    seen_notes = (primary.intent_notes or "").strip()
    for dup in dups:
        extra = (dup.intent_notes or "").strip()
        if extra and extra not in seen_notes:
            primary.intent_notes = (
                (primary.intent_notes or "").rstrip()
                + f"\n\n[Merged from lead #{dup.id}]: "
                + extra
            )[:20000]
            seen_notes = primary.intent_notes

    # Empty metadata keys are filled; primary values win.
    try:
        metadata = json.loads(primary.metadata_json or "{}")
        if not isinstance(metadata, dict):
            metadata = {}
    except (ValueError, TypeError):
        metadata = {}
    changed = False
    for dup in dups:
        try:
            other = json.loads(dup.metadata_json or "{}")
        except (ValueError, TypeError):
            other = {}
        if not isinstance(other, dict):
            continue
        for key, value in other.items():
            if key not in metadata or not str(metadata.get(key, "")).strip():
                metadata[key] = value
                changed = True
    if changed:
        primary.metadata_json = json.dumps(metadata, ensure_ascii=False)

    # Consent: keep the earliest recorded consent (both leads consented).
    times = [_utc(primary.consent_timestamp)] + [_utc(d.consent_timestamp) for d in dups]
    times = [t for t in times if t is not None]
    if times:
        primary.consent_timestamp = min(times)

    if not primary.referral_code:
        for dup in dups:
            if dup.referral_code:
                primary.referral_code = dup.referral_code
                break

    return planned_fills, planned_conflicts


def _merge_qualification(db: Session, primary: Lead, dups: list[Lead]) -> tuple[int, list[str], list[str]]:
    dup_ids = [d.id for d in dups]
    primary_q = db.scalar(select(LeadQualification).where(LeadQualification.lead_id == primary.id))
    dup_qs = list(
        db.scalars(
            select(LeadQualification)
            .where(LeadQualification.lead_id.in_(dup_ids))
            .order_by(LeadQualification.id.asc())
        ).all()
    )
    if primary_q is None and not dup_qs:
        return 0, [], []

    if primary_q is not None:
        base = primary_q
        others = dup_qs
    else:
        base = dup_qs[0]
        others = dup_qs[1:]
    filled, conflicts = _apply_q(base, others, primary.id)
    for row in others:
        db.delete(row)
    return (0 if primary_q is not None else 1), filled, conflicts


def _merge_deal(db: Session, primary: Lead, dups: list[Lead]) -> tuple[int, list[str]]:
    dup_ids = [d.id for d in dups]
    primary_deal = db.scalar(select(DealOutcome).where(DealOutcome.lead_id == primary.id))
    dup_deals = list(
        db.scalars(
            select(DealOutcome)
            .where(DealOutcome.lead_id.in_(dup_ids))
            .order_by(DealOutcome.id.asc())
        ).all()
    )
    if not dup_deals:
        return 0, []

    conflicts: list[str] = []
    if primary_deal is not None:
        for deal in dup_deals:
            conflicts.append(
                f"deal outcome kept on primary (lead #{deal.lead_id}: {deal.status} {deal.amount:g} {deal.currency} not summed)"
            )
            db.delete(deal)
        return 0, conflicts

    base = dup_deals[0]
    base.lead_id = primary.id
    base.user_id = primary.user_id
    for deal in dup_deals[1:]:
        conflicts.append(
            f"extra deal outcome not summed (lead #{deal.lead_id}: {deal.status} {deal.amount:g} {deal.currency})"
        )
        db.delete(deal)
    return 1, conflicts


def _merge_nurture(db: Session, primary: Lead, dups: list[Lead]) -> tuple[int, list[str]]:
    dup_ids = [d.id for d in dups]
    primary_campaigns = set(
        db.scalars(select(NurtureEnrollment.campaign_id).where(NurtureEnrollment.lead_id == primary.id)).all()
    )
    moved = 0
    conflicts: list[str] = []
    for enrollment in list(
        db.scalars(
            select(NurtureEnrollment)
            .where(NurtureEnrollment.lead_id.in_(dup_ids))
            .order_by(NurtureEnrollment.id.asc())
        ).all()
    ):
        if enrollment.campaign_id in primary_campaigns:
            conflicts.append(f"nurture enrollment in campaign #{enrollment.campaign_id} kept on primary")
            db.delete(enrollment)
        else:
            enrollment.lead_id = primary.id
            enrollment.user_id = primary.user_id
            primary_campaigns.add(enrollment.campaign_id)
            moved += 1
    return moved, conflicts


def _later(a: datetime.datetime | None, b: datetime.datetime | None) -> datetime.datetime | None:
    ua, ub = _utc(a), _utc(b)
    if ua is None:
        return b
    if ub is None:
        return a
    return a if ua >= ub else b


def _merge_conversations(db: Session, primary: Lead, dups: list[Lead]) -> tuple[int, int, int, list[str]]:
    dup_ids = [d.id for d in dups]
    primary_by_channel = {
        conv.channel: conv
        for conv in db.scalars(select(Conversation).where(Conversation.lead_id == primary.id)).all()
    }
    convs = list(
        db.scalars(
            select(Conversation).where(Conversation.lead_id.in_(dup_ids)).order_by(Conversation.id.asc())
        ).all()
    )
    messages = _count_messages(db, [c.id for c in convs])
    moved = merged = 0
    conflicts: list[str] = []

    for conv in convs:
        existing = primary_by_channel.get(conv.channel)
        if existing is None:
            conv.lead_id = primary.id
            primary_by_channel[conv.channel] = conv
            moved += 1
            continue
        db.execute(
            update(Message)
            .where(Message.conversation_id == conv.id)
            .values(conversation_id=existing.id)
            .execution_options(synchronize_session=False)
        )
        existing.last_message_at = _later(existing.last_message_at, conv.last_message_at)
        db.delete(conv)
        merged += 1
        conflicts.append(f"{conv.channel} conversation merged into the primary thread")

    return moved, merged, messages, conflicts


def _bump_activity(db: Session, primary: Lead, moved: dict, dups: list[Lead], conflicts: int) -> None:
    parts = [f"{key.replace('_', ' ')}={value}" for key, value in moved.items() if value]
    detail = (
        f"Duplicate merge: {len(dups)} lead(s) merged (#{', #'.join(str(d.id) for d in dups)}); "
        + (", ".join(parts) if parts else "no child records")
        + f"; conflicts={conflicts}"
    )[:500]
    db.add(
        LeadActivity(
            lead_id=primary.id,
            user_id=primary.user_id,
            kind="duplicate_merged",
            detail=detail,
        )
    )


def merge(db: Session, user: User, primary_id: int, duplicate_ids: list[int], dry_run: bool = False) -> dict:
    ids = list(dict.fromkeys(duplicate_ids))
    if not ids:
        raise ValueError("Provide at least one duplicate lead id.")
    if len(ids) > MERGE_LIMIT:
        raise ValueError(f"Merge at most {MERGE_LIMIT} duplicates at a time.")
    if primary_id in ids:
        raise ValueError("The primary lead cannot also be a duplicate.")

    wanted = [primary_id] + ids
    found = {
        lead.id: lead
        for lead in db.scalars(select(Lead).where(Lead.id.in_(wanted), Lead.user_id == user.id)).all()
    }
    missing = [lead_id for lead_id in wanted if lead_id not in found]
    if missing:
        raise LookupError(missing)

    primary = found[primary_id]
    dups = [found[lead_id] for lead_id in ids]

    preview = _preview(db, primary, dups)
    if dry_run:
        return {
            "merged": False,
            "dry_run": True,
            **preview,
            "notes": [
                "Preview only - nothing was changed.",
                "Deal outcomes are never summed; the primary's outcome wins.",
                "Known qualification values on the primary are never overwritten.",
            ],
        }

    try:
        moved: dict[str, int] = {}
        for model, key in (
            (LeadNote, "notes"),
            (LeadStageHistory, "stage_history"),
            (LeadActivity, "activities"),
            (LeadScoreHistory, "score_history"),
            (Appointment, "appointments"),
            (ReviewRequest, "review_requests"),
            (WebhookEvent, "webhook_events"),
        ):
            result = db.execute(
                update(model)
                .where(model.lead_id.in_(ids))
                .values(lead_id=primary.id)
                .execution_options(synchronize_session=False)
            )
            moved[key] = int(result.rowcount or 0)

        # Referrals: anyone who named a duplicate as their referrer now points
        # at the primary. The primary's own referrer is fixed up afterwards so
        # it can never become a self-referral.
        referred = db.execute(
            update(Lead)
            .where(Lead.referred_by_lead_id.in_(ids))
            .values(referred_by_lead_id=primary.id)
            .execution_options(synchronize_session=False)
        )
        moved["referred_leads"] = int(referred.rowcount or 0)
        if primary.referred_by_lead_id in ids:
            referrer = next(
                (d.referred_by_lead_id for d in dups if d.id == primary.referred_by_lead_id), None
            )
            primary.referred_by_lead_id = (
                referrer if referrer and referrer not in ids and referrer != primary.id else None
            )

        moved["qualifications"], q_fills, q_conflicts = _merge_qualification(db, primary, dups)
        moved["deal_outcomes"], deal_conflicts = _merge_deal(db, primary, dups)
        moved["nurture_enrollments"], nurture_conflicts = _merge_nurture(db, primary, dups)
        (
            moved["conversations"],
            moved["conversations_merged"],
            moved["messages"],
            conversation_conflicts,
        ) = _merge_conversations(db, primary, dups)

        fills, field_conflicts = _fill_primary(primary, dups)
        conflicts = q_conflicts + deal_conflicts + nurture_conflicts + conversation_conflicts + field_conflicts

        db.flush()
        for dup in dups:
            db.delete(dup)
        db.flush()

        _bump_activity(db, primary, moved, dups, len(conflicts))
        audit_svc.record(
            db,
            user,
            "lead.merged",
            target_type="lead",
            target_id=primary.id,
            detail={
                "primary_id": primary.id,
                "duplicate_ids": ids,
                "moved": moved,
                "fields_filled": fills,
                "conflicts": len(conflicts),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    capped = conflicts[:CONFLICT_LIMIT]
    if len(conflicts) > CONFLICT_LIMIT:
        capped.append(f"... and {len(conflicts) - CONFLICT_LIMIT} more conflict note(s)")

    return {
        "merged": True,
        "dry_run": False,
        "primary": _row(primary),
        "duplicates": [_row(d) for d in dups],
        "moved": moved,
        "fields_filled": fills,
        "conflicts": capped,
        "notes": [
            "Duplicate lead rows were deleted after their history moved to the primary.",
            "Revenue was not summed; only the primary's recorded outcome counts.",
            "The merge is on the primary lead's timeline and in the workspace audit log.",
        ],
    }
