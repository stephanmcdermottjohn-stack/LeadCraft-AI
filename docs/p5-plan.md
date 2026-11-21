# P5 #1 — Booking & appointments (zero-cost, owner-operated)

Goal: let a business publish bookable time slots on its landing page and manage
the resulting appointments, without paying for a scheduling service and without
pretending the platform talks to customers.

Every roadmap ground rule still holds: consent-based only, `source` +
`consent_timestamp` on every lead, tenant isolation on every endpoint, honest
labels (unknown is not zero), no outbound-first contact, no auto-send.

## Module 1 — Booking availability (shipped)

Owner-controlled weekly schedule stored on `clients_settings`:

- `booking_enabled` (default **false**), `booking_days_json` (0=Monday…6=Sunday),
  `booking_start` / `booking_end` (`HH:MM`), `booking_slot_minutes` (15–180),
  `booking_lead_minutes` (minimum notice, 0–10080), `booking_timezone`
  (IANA, default `Asia/Karachi`), `booking_services_json` (max 10 names),
  `booking_note` (max 300 chars, shown to visitors).
- Slots are generated **server-side** inside the workspace timezone and returned
  as UTC ISO timestamps plus a server-rendered local label. The browser never
  computes or invents available times.
- Booking disabled → the landing page shows no booking widget, the public slots
  endpoint returns `enabled: false` with an empty list, and booking attempts are
  refused (400).
- Booking window: today … today + 60 days; past dates, closed weekdays, and
  times inside the minimum-notice window return no slots.
- Role gates: reading availability is workspace-wide; `PATCH
  /api/appointments/availability` is **owner/admin/manager** only. Agents can
  still view and run appointments; viewers are read-only (existing global gate).

## Module 2 — Public booking (shipped)

- `GET /api/public/landing/{slug}/slots?date=YYYY-MM-DD` — no auth. Returns the
  slot list, services, slot length, timezone, and a hint that the platform
  sends no confirmation. Unknown slug → 404; malformed date → 400.
- `POST /api/public/landing/{slug}/book` — no auth, 201. Requires
  `starts_at` (one of the server's returned slots), `name`, `consent: true`, and
  a phone or email. Honeypot `company` silently rejected (same contract as the
  lead capture form).
- Validation: an arbitrary/forged time, a closed day, a too-soon time, or an
  already-booked slot → **409** with "pick another time". Consent missing → 400.
- Lead handling: the booking reuses an existing lead by normalized phone, then
  by email; otherwise it creates one with `source='landing_page'`,
  `metadata.entry_point='booking'` (+ service and appointment time), and a
  server-side `consent_timestamp`. Stage history is appended.
- Response states plainly: the business will contact the visitor to confirm and
  **the platform does not send confirmation or reminder messages**.

## Module 3 — Appointments (shipped)

`appointments` table (all rows workspace-scoped by `user_id`, FK to `leads`):

- `starts_at` / `ends_at` (UTC, `TIMESTAMPTZ`), `service`, `source`
  (`public_booking` | `manual`), `status`
  (`booked | confirmed | completed | cancelled | no_show`), `owner_notes`,
  `reminded_at` (manual marker), timestamps.
- Double booking of the same start time is refused (409) against active
  (`booked`, `confirmed`) rows; cancelled/no-show/completed free the slot.
- `GET /api/appointments?status=&date_from=&date_to=&limit=` — workspace list,
  soonest first, includes customer name/phone/email from the linked lead, the
  workspace timezone, and the honesty note.
- `GET /api/appointments/slots?date=` — owner preview of the public slot list.
- `POST /api/appointments` — manual entry (phone/walk-in). No working-hours
  restriction (the owner is in control), but the time must be in the future,
  free, `consent: true` must be attested by the team, and name + one contact are
  required. Creates or reuses a lead with `source='direct_message'`,
  `metadata.entry_point='manual_appointment'`.
- `PATCH /api/appointments/{id}` — status, owner notes, and the `reminded`
  boolean. Every status change appends a `LeadActivity` timeline entry.
  `reminded_at` is purely a marker; nothing is sent.
- Tenant isolation: cross-workspace ids → 404; unauthenticated → 401; viewers →
  403 on writes.

## Module 4 — UI (shipped)

- New **Appointments** nav item.
- Availability editor: enable toggle, weekday buttons, opens/closes, slot
  length, minimum notice, IANA timezone, comma-separated services, visitor note.
  Read-only (with an explicit message) for roles that cannot edit.
- Appointment table: local-time display, customer, service, status actions,
  "mark reminder" toggle, team-entered label.
- Manual add form with the consent attestation.
- Landing page: when booking is enabled, the capture form offers
  "Book an appointment" — date picker → server slots → service/name/phone/
  email/notes → consent → confirmation with the honest no-message statement.

## Honest scope / out of scope (not built)

- **No SMS, email, or WhatsApp confirmation/reminder is sent by the platform.**
  There is no reminder scheduler; `reminded_at` records that the owner contacted
  the customer themselves.
- No payment/deposit collection, no calendar sync (Google/Outlook), no iCal
  feed, no recurring appointments, no staff/resource assignment, no waitlist.
- No timezone auto-detection: the workspace timezone is explicit, and visitors
  are told which timezone the times are in.
- No customer self-service cancel/reschedule link (cancellations are owner-side).

## Activation (owner)

1. Appointments → **Booking availability**: enable, pick weekdays, set hours,
   slot length, minimum notice, services and a note. Save.
2. Share `/l/<slug>`; the landing page now offers a fixed time.
3. Treat status + reminder marker as the owner's own workflow; contact the
   customer through the business's normal channel.

## Migration

`backend/scripts/add_booking.py` (idempotent): adds the nine booking columns to
`clients_settings` and creates `appointments` with indexes on `user_id`,
`lead_id`, `starts_at`, `status`. `tzdata` was added to `requirements.txt`
because Windows lacks the IANA database.
