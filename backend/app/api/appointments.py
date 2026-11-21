"""Appointment management (P5 #1).

Role rules: viewing and day-to-day status changes are operational (agent ok);
changing hours/services/enabling booking is business configuration (owner,
admin or manager only). Viewers are already blocked from writes globally.
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import get_db
from app.models import Appointment, ClientSettings, User
from app.services import booking as svc

router = APIRouter(prefix="/api/appointments")

CONFIG_ROLES = ("owner", "admin", "manager")


class AvailabilityBody(BaseModel):
    enabled: bool | None = None
    days: list[int] | None = None
    start: str | None = Field(default=None, max_length=5)
    end: str | None = Field(default=None, max_length=5)
    slot_minutes: int | None = None
    lead_minutes: int | None = None
    timezone: str | None = Field(default=None, max_length=64)
    services: list[str] | None = None
    note: str | None = Field(default=None, max_length=300)


class AppointmentStatusBody(BaseModel):
    status: str | None = Field(default=None, max_length=20)
    owner_notes: str | None = Field(default=None, max_length=1000)
    reminded: bool | None = None


class ManualAppointmentBody(BaseModel):
    starts_at: datetime.datetime
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=320)
    service: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=1000)
    consent: bool


def _role(user: User) -> str:
    return getattr(user, "workspace_role", "owner")


def _require_config(user: User) -> None:
    if _role(user) not in CONFIG_ROLES:
        raise HTTPException(status_code=403, detail="Owner, admin or manager role required for booking settings.")


def _settings_row(db: Session, user: User) -> ClientSettings:
    row = db.scalar(select(ClientSettings).where(ClientSettings.user_id == user.id))
    if row is None:
        row = ClientSettings(user_id=user.id)
        db.add(row)
        db.flush()
    return row


def _owned(db: Session, appointment_id: int, user: User) -> Appointment:
    row = db.get(Appointment, appointment_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return row


def _parse_day(value: str, field: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD.")


@router.get("/availability")
def get_availability(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = _settings_row(db, user)
    db.commit()
    return {"availability": svc.availability_public(row), "can_edit": _role(user) in CONFIG_ROLES}


@router.patch("/availability")
def update_availability(
    body: AvailabilityBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    _require_config(user)
    row = _settings_row(db, user)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        svc.update_availability(row, payload)
    except svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return {"availability": svc.availability_public(row), "can_edit": True}


@router.get("/slots")
def get_slots(
    date: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Owner preview of the public slot list (useful before enabling)."""
    row = _settings_row(db, user)
    db.commit()
    try:
        slots = svc.slots_for_date(db, row, date)
    except svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return {"date": date, "timezone": row.booking_timezone, "enabled": bool(row.booking_enabled), "slots": slots}


@router.get("")
def list_appointments(
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    limit = max(1, min(limit, 500))
    stmt = select(Appointment).where(Appointment.user_id == user.id)
    if status:
        if status not in svc.STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(svc.STATUSES)}")
        stmt = stmt.where(Appointment.status == status)
    if date_from:
        start = _parse_day(date_from, "date_from")
        stmt = stmt.where(
            Appointment.starts_at
            >= datetime.datetime.combine(start, datetime.time.min, tzinfo=datetime.timezone.utc)
        )
    if date_to:
        end = _parse_day(date_to, "date_to") + datetime.timedelta(days=1)
        stmt = stmt.where(
            Appointment.starts_at
            < datetime.datetime.combine(end, datetime.time.min, tzinfo=datetime.timezone.utc)
        )
    rows = db.scalars(stmt.order_by(Appointment.starts_at.asc()).limit(limit)).all()
    return {
        "appointments": [svc.appointment_public(a) for a in rows],
        "count": len(rows),
        "statuses": list(svc.STATUSES),
        "timezone": _settings_row(db, user).booking_timezone,
        "note": svc.HONESTY,
    }


@router.post("", status_code=201)
def create_manual(
    body: ManualAppointmentBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    row = _settings_row(db, user)
    try:
        appointment, lead, created = svc.create_manual(
            db,
            row,
            starts_at=body.starts_at,
            name=body.name,
            phone=body.phone,
            email=body.email,
            service=body.service,
            notes=body.notes,
            consent=body.consent,
        )
    except svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return {
        "appointment": svc.appointment_public(appointment),
        "lead_created": created,
        "lead_id": lead.id,
        "note": "Appointment recorded. The platform sends no confirmation message.",
    }


@router.patch("/{appointment_id}")
def update_appointment(
    appointment_id: int,
    body: AppointmentStatusBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    appointment = _owned(db, appointment_id, user)
    try:
        svc.status_change(db, appointment, body.model_dump(exclude_none=True))
    except svc.BookingError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    db.refresh(appointment)
    return {
        "appointment": svc.appointment_public(appointment),
        "note": "Reminder marker is manual - the platform sends nothing.",
    }
