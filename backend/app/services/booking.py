"""Booking & appointments (P5 #1) - zero-cost, owner-operated.

Honest scope, stated in the API payload and UI:

- The platform never sends a confirmation, reminder or cancellation SMS/email.
  `reminded_at` is a manual marker the owner sets after contacting the customer.
- Slots exist only inside the workspace's working hours and chosen weekdays;
  the server regenerates and validates them, so the public endpoint cannot be
  used to create arbitrary appointment times.
- Appointment creation is consent-first: the public form requires an explicit
  consent checkbox, and `consent_timestamp` is stamped server-side. Manual
  entries require the owner to attest consent (same rule as CSV import).
"""
import datetime
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, ClientSettings, Lead, LeadActivity, LeadStageHistory

STATUSES = ("booked", "confirmed", "completed", "cancelled", "no_show")
ACTIVE_STATUSES = ("booked", "confirmed")
MAX_DAYS_AHEAD = 60
SERVICES_MAX = 10

HONESTY = (
    "The platform sends no SMS, email or WhatsApp confirmations/reminders. "
    "Any reminder is sent by the business through its own channel and marked manually."
)


class BookingError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _norm_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def parse_days(raw: str) -> list[int]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return sorted({int(d) for d in data if isinstance(d, int) and 0 <= d <= 6})


def parse_services(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [str(s).strip()[:100] for s in data if str(s).strip()][:SERVICES_MAX]


def _parse_hhmm(value: str, field: str) -> datetime.time:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value or ""):
        raise BookingError(f"{field} must be HH:MM (24-hour).")
    return datetime.time.fromisoformat(value)


def timezone_of(row: ClientSettings) -> ZoneInfo:
    try:
        return ZoneInfo(row.booking_timezone or "Asia/Karachi")
    except (ZoneInfoNotFoundError, ValueError):
        raise BookingError("booking_timezone is not a valid IANA timezone (e.g. Asia/Karachi).")


def availability_public(row: ClientSettings) -> dict:
    return {
        "enabled": bool(row.booking_enabled),
        "slot_minutes": int(row.booking_slot_minutes or 30),
        "start": row.booking_start or "10:00",
        "end": row.booking_end or "18:00",
        "days": parse_days(row.booking_days_json),
        "timezone": row.booking_timezone or "Asia/Karachi",
        "services": parse_services(row.booking_services_json),
        "lead_minutes": int(row.booking_lead_minutes or 0),
        "note": row.booking_note or "",
        "max_days_ahead": MAX_DAYS_AHEAD,
        "disclaimer": HONESTY,
    }


def landing_booking_config(row: ClientSettings) -> dict:
    """Only what the public landing page needs (no owner data)."""
    data = availability_public(row)
    data.pop("disclaimer", None)
    return data


def update_availability(row: ClientSettings, body: dict) -> None:
    """Validate + persist the weekly schedule. Owner/admin/manager only (route)."""
    if "enabled" in body and body["enabled"] is not None:
        row.booking_enabled = bool(body["enabled"])

    days = body.get("days")
    if days is not None:
        if not isinstance(days, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in days):
            raise BookingError("days must be a list of integers 0-6 (0=Monday).")
        normalised = sorted(set(days))
        if row.booking_enabled and not normalised:
            raise BookingError("Pick at least one working day before enabling booking.")
        row.booking_days_json = json.dumps(normalised)

    if body.get("start") is not None:
        _parse_hhmm(body["start"], "start")
        row.booking_start = body["start"]
    if body.get("end") is not None:
        _parse_hhmm(body["end"], "end")
        row.booking_end = body["end"]

    start = _parse_hhmm(row.booking_start or "10:00", "start")
    end = _parse_hhmm(row.booking_end or "18:00", "end")
    if end <= start:
        raise BookingError("end must be after start.")

    if body.get("slot_minutes") is not None:
        try:
            minutes = int(body["slot_minutes"])
        except (TypeError, ValueError):
            raise BookingError("slot_minutes must be an integer.")
        if minutes < 15 or minutes > 180:
            raise BookingError("slot_minutes must be between 15 and 180.")
        row.booking_slot_minutes = minutes
    if row.booking_slot_minutes and row.booking_slot_minutes < 15:
        raise BookingError("slot_minutes must be between 15 and 180.")

    if body.get("lead_minutes") is not None:
        try:
            lead = int(body["lead_minutes"])
        except (TypeError, ValueError):
            raise BookingError("lead_minutes must be an integer.")
        if lead < 0 or lead > 10080:
            raise BookingError("lead_minutes must be between 0 and 10080 (one week).")
        row.booking_lead_minutes = lead

    if body.get("timezone") is not None:
        value = str(body["timezone"]).strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise BookingError("timezone must be a valid IANA name, e.g. Asia/Karachi.")
        row.booking_timezone = value

    if body.get("services") is not None:
        services = body["services"]
        if not isinstance(services, list):
            raise BookingError("services must be a list of names.")
        cleaned: list[str] = []
        for item in services:
            name = str(item).strip()[:100]
            if name and name not in cleaned:
                cleaned.append(name)
        if len(cleaned) > SERVICES_MAX:
            raise BookingError(f"At most {SERVICES_MAX} services are supported.")
        row.booking_services_json = json.dumps(cleaned)

    if body.get("note") is not None:
        row.booking_note = str(body["note"]).strip()[:300]

    if row.booking_enabled and not parse_days(row.booking_days_json):
        raise BookingError("Pick at least one working day before enabling booking.")


def slots_for_date(
    db: Session,
    row: ClientSettings,
    date_str: str,
    now: datetime.datetime | None = None,
) -> list[dict]:
    """Available slots for one local date, computed server-side.

    Returns `[]` for disabled booking, non-working days and dates outside the
    60-day window. Invalid dates are a 400 (public clients send our own date).
    """
    if not row.booking_enabled:
        return []
    try:
        local_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        raise BookingError("date must be YYYY-MM-DD.")
    tz = timezone_of(row)
    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    today = now.astimezone(tz).date()
    if local_date < today or local_date > today + datetime.timedelta(days=MAX_DAYS_AHEAD):
        return []
    if local_date.weekday() not in parse_days(row.booking_days_json):
        return []

    start_t = _parse_hhmm(row.booking_start or "10:00", "start")
    end_t = _parse_hhmm(row.booking_end or "18:00", "end")
    step = int(row.booking_slot_minutes or 30)
    if step < 15 or step > 180 or end_t <= start_t:
        return []

    day_start = datetime.datetime.combine(local_date, start_t, tzinfo=tz)
    day_end = datetime.datetime.combine(local_date, end_t, tzinfo=tz)
    earliest = now + datetime.timedelta(minutes=int(row.booking_lead_minutes or 0))

    window_start = day_start.astimezone(datetime.timezone.utc)
    window_end = day_end.astimezone(datetime.timezone.utc)
    rows = db.scalars(
        select(Appointment).where(
            Appointment.user_id == row.user_id,
            Appointment.status.in_(ACTIVE_STATUSES),
            Appointment.starts_at >= window_start,
            Appointment.starts_at < window_end,
        )
    ).all()
    taken = {_as_utc(a.starts_at).replace(second=0, microsecond=0) for a in rows}

    out: list[dict] = []
    cursor = day_start
    while cursor + datetime.timedelta(minutes=step) <= day_end:
        utc = cursor.astimezone(datetime.timezone.utc)
        if utc >= earliest and utc.replace(second=0, microsecond=0) not in taken:
            out.append(
                {
                    "starts_at": utc.isoformat(),
                    "ends_at": (utc + datetime.timedelta(minutes=step)).isoformat(),
                    "label": cursor.strftime("%I:%M %p").lstrip("0"),
                }
            )
        cursor = cursor + datetime.timedelta(minutes=step)
    return out


def _find_lead(db: Session, user_id: int, phone: str, email: str) -> Lead | None:
    target = _norm_phone(phone)
    if target:
        for lead in db.scalars(select(Lead).where(Lead.user_id == user_id).order_by(Lead.id.desc())).all():
            if _norm_phone(lead.phone) == target:
                return lead
    if email:
        return db.scalar(
            select(Lead)
            .where(Lead.user_id == user_id, Lead.email == email.strip().lower())
            .order_by(Lead.id.desc())
        )
    return None


def _assert_slot_free(db: Session, user_id: int, starts_at: datetime.datetime) -> None:
    existing = db.scalar(
        select(Appointment).where(
            Appointment.user_id == user_id,
            Appointment.starts_at == starts_at,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    )
    if existing is not None:
        raise BookingError("That slot has just been booked. Please pick another time.", status=409)


def create_booking(
    db: Session,
    row: ClientSettings,
    *,
    starts_at: datetime.datetime,
    name: str,
    phone: str,
    email: str,
    service: str,
    intent_notes: str,
    consent: bool,
    now: datetime.datetime | None = None,
) -> tuple[Appointment, Lead, bool]:
    """Public booking. Server-side slot validation + consent-first lead."""
    if not row.booking_enabled:
        raise BookingError("Booking is not enabled for this business.")
    if not consent:
        raise BookingError("Consent is required to book an appointment.")
    name = (name or "").strip()[:200]
    phone = (phone or "").strip()[:50]
    email = (email or "").strip().lower()[:320]
    if not name:
        raise BookingError("name is required.")
    if not phone and not email:
        raise BookingError("Provide a phone number or an email so the business can confirm.")

    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    tz = timezone_of(row)
    local_date = _as_utc(starts_at).astimezone(tz).date().isoformat()
    available = slots_for_date(db, row, local_date, now=now)
    match = next(
        (s for s in available if datetime.datetime.fromisoformat(s["starts_at"]) == _as_utc(starts_at)),
        None,
    )
    if match is None:
        raise BookingError("That time is not an available slot. Refresh the slots and pick another.", status=409)

    start_utc = _as_utc(starts_at)
    _assert_slot_free(db, row.user_id, start_utc)
    end_utc = start_utc + datetime.timedelta(minutes=int(row.booking_slot_minutes or 30))

    lead = _find_lead(db, row.user_id, phone, email)
    created_lead = False
    if lead is None:
        lead = Lead(
            user_id=row.user_id,
            source="landing_page",
            name=name,
            phone=phone,
            email=email,
            area="",
            intent_notes=(intent_notes or "").strip()[:2000],
            consent_timestamp=now,
            score=0,
            status="new",
            lifecycle_stage="capture",
            metadata_json=json.dumps(
                {
                    "entry_point": "booking",
                    "service": (service or "").strip()[:100],
                    "appointment_at": start_utc.isoformat(),
                }
            ),
            created_at=now,
        )
        db.add(lead)
        db.flush()
        db.add(
            LeadStageHistory(
                lead_id=lead.id,
                user_id=row.user_id,
                from_stage="",
                to_stage="capture",
                note="captured via landing-page booking",
            )
        )
        created_lead = True
    else:
        if not lead.consent_timestamp:
            lead.consent_timestamp = now

    appointment = Appointment(
        user_id=row.user_id,
        lead_id=lead.id,
        starts_at=start_utc,
        ends_at=end_utc,
        service=(service or "").strip()[:100],
        source="public_booking",
        status="booked",
        created_at=now,
    )
    db.add(appointment)
    db.flush()
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=row.user_id,
            kind="appointment_booked",
            detail=f"{appointment.service or 'Appointment'} at {start_utc.isoformat()} (public booking)",
        )
    )
    return appointment, lead, created_lead


def create_manual(
    db: Session,
    row: ClientSettings,
    *,
    starts_at: datetime.datetime,
    name: str,
    phone: str,
    email: str,
    service: str,
    notes: str,
    consent: bool,
    now: datetime.datetime | None = None,
) -> tuple[Appointment, Lead, bool]:
    """Owner-entered appointment (phone/walk-in booking).

    No working-hours restriction (the owner is in control), but the time must
    be in the future, free, and the owner must attest consent.
    """
    if not consent:
        raise BookingError("Confirm that the customer agreed to be contacted and booked.")
    name = (name or "").strip()[:200]
    phone = (phone or "").strip()[:50]
    email = (email or "").strip().lower()[:320]
    if not name:
        raise BookingError("name is required.")
    if not phone and not email:
        raise BookingError("Provide a phone number or an email.")

    now = _as_utc(now or datetime.datetime.now(datetime.timezone.utc))
    start_utc = _as_utc(starts_at)
    if start_utc <= now:
        raise BookingError("starts_at must be in the future.")
    _assert_slot_free(db, row.user_id, start_utc)
    end_utc = start_utc + datetime.timedelta(minutes=int(row.booking_slot_minutes or 30))

    lead = _find_lead(db, row.user_id, phone, email)
    created_lead = False
    if lead is None:
        lead = Lead(
            user_id=row.user_id,
            source="direct_message",
            name=name,
            phone=phone,
            email=email,
            area="",
            intent_notes="",
            consent_timestamp=now,
            score=0,
            status="new",
            lifecycle_stage="capture",
            metadata_json=json.dumps({"entry_point": "manual_appointment"}),
            created_at=now,
        )
        db.add(lead)
        db.flush()
        db.add(
            LeadStageHistory(
                lead_id=lead.id,
                user_id=row.user_id,
                from_stage="",
                to_stage="capture",
                note="captured via team-entered appointment",
            )
        )
        created_lead = True

    appointment = Appointment(
        user_id=row.user_id,
        lead_id=lead.id,
        starts_at=start_utc,
        ends_at=end_utc,
        service=(service or "").strip()[:100],
        source="manual",
        status="booked",
        owner_notes=(notes or "").strip()[:1000],
        created_at=now,
    )
    db.add(appointment)
    db.flush()
    db.add(
        LeadActivity(
            lead_id=lead.id,
            user_id=row.user_id,
            kind="appointment_booked",
            detail=f"{appointment.service or 'Appointment'} at {start_utc.isoformat()} (team entered)",
        )
    )
    return appointment, lead, created_lead


def appointment_public(a: Appointment) -> dict:
    lead = a.lead
    return {
        "id": a.id,
        "lead_id": a.lead_id,
        "lead_name": lead.name if lead else "",
        "lead_phone": lead.phone if lead else "",
        "lead_email": lead.email if lead else "",
        "starts_at": _as_utc(a.starts_at).isoformat() if a.starts_at else None,
        "ends_at": _as_utc(a.ends_at).isoformat() if a.ends_at else None,
        "service": a.service,
        "source": a.source,
        "status": a.status,
        "owner_notes": a.owner_notes,
        "reminded_at": a.reminded_at.isoformat() if a.reminded_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def status_change(db: Session, appointment: Appointment, body: dict) -> Appointment:
    if body.get("status") is not None:
        status = str(body["status"]).strip()
        if status not in STATUSES:
            raise BookingError(f"status must be one of: {', '.join(STATUSES)}")
        if status != appointment.status:
            appointment.status = status
            db.add(
                LeadActivity(
                    lead_id=appointment.lead_id,
                    user_id=appointment.user_id,
                    kind="appointment_status",
                    detail=f"Appointment {appointment.id}: {status}",
                )
            )
    if body.get("owner_notes") is not None:
        appointment.owner_notes = str(body["owner_notes"]).strip()[:1000]
    if body.get("reminded") is not None:
        appointment.reminded_at = (
            datetime.datetime.now(datetime.timezone.utc) if body["reminded"] else None
        )
    return appointment
