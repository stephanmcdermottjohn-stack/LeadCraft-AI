# P5 #2 — Data, audit & ops (zero-cost)

Goal: give the workspace owner real control over their own data — download it,
see who changed what, remove stale anonymous telemetry, and understand usage —
without adding a paid provider, an external metering service, or any new
compliance claim the platform cannot back up.

Roles: **owner/admin only** for every `/api/ops` route (exports contain customer
contact data; the audit log contains team actions; retention is irreversible).
Agents/viewers → 403, unauthenticated → 401. Every route is tenant-scoped.

## Module 1 — Workspace export (shipped)

`GET /api/ops/export` returns a JSON attachment
(`leadcraft-workspace-<id>-<timestamp>.json`) containing the workspace's own:

- profile (business name, login email, plan label, created date) and settings
  (landing/booking/branding/integration routing ids — **no secrets**),
- leads, notes, stage history, activities, BANT qualification, score history,
- appointments,
- content posts,
- conversations + messages (scoped through their lead),
- review requests, campaign spend, nurture campaigns/enrollments/suppressions,
- manual billing entries,
- team members (**invite tokens stripped**),
- routed webhook deliveries.

Honest limits, stated inside the file:

- Each table is capped at **5,000 rows**; `truncated_tables` lists any table
  that hit the cap.
- Anonymous telemetry (`landing_events`, `analytics_events`) is **excluded** —
  it is high-volume and contains no business records; the retention tool
  removes it instead.
- `users.password_hash` and single-use team invite tokens are never exported.
- The export is logged in the audit trail (`ops.export`).

## Module 2 — Workspace audit log (shipped)

New append-only `audit_logs` table: workspace id, actual actor account + email,
action, target type/id, JSON detail, timestamp. There is **no update or delete
endpoint** by design.

Recorded actions (workspace-level only):

| Action | When |
|---|---|
| `settings.updated` | `PATCH /api/settings` (stores changed **keys**, not values) |
| `team.invited` / `team.joined` / `team.role_changed` / `team.removed` | team management, attributed to the real account |
| `billing.entry_added` / `billing.entry_deleted` / `billing.plan_changed` | manual ledger |
| `booking.availability_updated` | booking hours/services changed (keys only) |
| `ops.export` / `ops.retention_purged` | data operations |

Lead-level edits are **not duplicated** here: they already have their own
append-only record (`lead_stage_history`, `lead_activities`) and the lead
timeline. Details never include passwords, tokens or message bodies.

`GET /api/ops/audit?action=&limit=` returns newest-first entries, the distinct
actions seen, and an explicit statement that the log is append-only and
workspace-scoped.

## Module 3 — Telemetry retention (shipped)

`GET /api/ops/retention/preview?days=30..3650` shows what would be deleted
(counts + cutoff). `POST /api/ops/retention/purge` with `{days, confirm: true}`
deletes only:

- `landing_events` older than the cutoff (anonymous A/B impressions),
- `analytics_events` older than the cutoff (cookie-free page analytics),
- `webhook_events` older than the cutoff whose status is `processed` or
  `ignored` (retryable rows are kept).

**Never purged:** leads, consent timestamps, notes, stage history, activities,
qualifications, appointments, content, billing, team records, the audit log.
`confirm: false` → 400. The purge writes an `ops.retention_purged` audit row
with the deleted counts.

## Module 4 — Usage (shipped)

`GET /api/ops/usage` returns row counts for the workspace (leads, appointments,
content, notes, conversations/messages, reviews, webhooks, telemetry, active
team members) and last-activity timestamps. Honest labels: counts are database
rows **for this workspace only**, not storage bytes, and no external metering
provider is queried.

## Frontend (shipped)

Settings → **Data, audit & ops** card: workspace JSON download, usage grid,
retention days input + preview + delete (with a confirmation dialog), and the
audit table. Non-owner/admin sees an explicit role notice instead of data.

## Out of scope (not built)

- Scheduled/automatic retention (purges are manual, owner-triggered).
- File storage export (there is no uploaded-media store).
- Legal/GDPR workflow automation or deletion certificates.
- Per-lead audit duplication, admin cross-workspace audit browsing.
- CSV audit export, log shipping, or any external observability provider.
