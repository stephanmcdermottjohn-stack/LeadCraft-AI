# AI LeadFlow — P3 execution plan (Commercial Scale)

Roadmap line (the only detail we have):

> **P3 — Commercial Scale:** Agency workspaces, white-label, billing,
> enterprise permissions.

P0–P2 are shipped and live (105/105 tests). P3 keeps every ground rule:
**additive only, zero required external cost, no scraping, consent-first,
honest labels, tenant isolation on every route.**

The hard constraint: the current tenancy model is **`User` = one business**.
Every route scopes data with `user.id`, and `ClientSettings` is 1:1 with the
account. A true "agency owns many client workspaces" model needs a
`workspace` table and a `workspace_id` on every data table — an invasive
migration. That is therefore **design-only in this phase** (Section 4) and is
not built without explicit approval.

The zero-cost, additive modules below ship first.

## Module order

1. **Team members & roles v1** (enterprise permissions, this increment) —
   invite a teammate into the existing workspace, role-based write gates,
   owner stays the data scope. No new tenancy tables.
2. **White-label branding v1** — brand name, logo URL, primary colour, support
   email, footer text, "hide platform brand" toggle on the app + landing
   page. Presentation only; billing state is not implied. **Shipped.**
3. **Manual billing ledger v1** — owner/admin-entered plan + invoice/payment
   rows (amount, currency, period, paid-until). **No payment gateway, no card
   data, no auto-charging.** The UI states this plainly. **Shipped.**
4. *(Design-only, approval gate)* **Agency multi-workspace** — account vs
   workspace split, `workspace_id` migration path, cost/effort estimate. No
   code until approved. Design: `docs/p3-agency-design.md`.

## Module 1 scope — team members & roles v1

**Status: shipped.** Implementation lives in `app/services/team.py`,
`app/api/team.py`, `scripts/add_team.py`, `tests/test_team.py`.

### Model
`workspace_members`:
`id, owner_user_id, member_user_id (nullable until accepted), invited_email,
role (admin|manager|agent|viewer), status (invited|active|removed),
invite_token (random, single-use by status), created_at, accepted_at`.
One row per `(owner_user_id, invited_email)`; unique active `member_user_id`
(a person belongs to one workspace at a time in v1).

### How scoping stays intact
`get_current_user` resolves an **active** membership for the logged-in account
and returns the **workspace owner** `User` — so every existing endpoint that
uses `user.id` automatically reads/writes workspace data. The resolved owner
object carries transient `workspace_role` / `workspace_account_id` attributes
for permission checks. Owner sessions resolve to themselves with role
`owner`. No data table changes, no dual-write.

### Roles (v1 truth table)
| Capability | owner | admin | manager | agent | viewer |
|---|---|---|---|---|---|
| Read workspace data | ✅ | ✅ | ✅ | ✅ | ✅ |
| Write leads / inbox / reviews / referrals / nurture / scoring | ✅ | ✅ | ✅ | ✅ | ❌ |
| Business settings + landing A/B config + campaign spend | ✅ | ✅ | ✅ | ❌ | ❌ |
| Invite / change role / remove members | ✅ | ✅ | ❌ | ❌ | ❌ |
| Ownership transfer / delete workspace | not in v1 | ❌ | ❌ | ❌ | ❌ |

Viewer writes are rejected at the auth dependency (403) except `/api/auth/*`.
Agent config writes are rejected for `/api/settings`, `/api/landing-ab`,
`/api/campaign-spend`.

### Invite flow (no email sending)
1. Owner/admin enters email + role -> `POST /api/team/invite`.
2. If the email already belongs to an account **with its own leads**, the
   invite is refused (that account owns data; silently re-scoping it would
   hide their workspace). Otherwise a pending row + random token is created.
3. The response returns `invite_path` (`/settings?invite=<token>`); the
   owner shares it however they like. **The platform sends nothing.**
4. The invited person logs in / registers, opens Settings, pastes the token
   (pre-filled from `?invite=`) and calls `POST /api/team/accept`.
5. Acceptance is only possible with the matching account email; the account
   must not already own leads or belong to another active workspace.
6. Removed members fall back to their own (empty) personal workspace.

### APIs
- `GET /api/team` — workspace summary + owner row + members (token shown to
  owner/admin only), `my_role`.
- `POST /api/team/invite` — owner/admin only; `{email, role}`; upserts a
  pending invite (re-invite rotates the token).
- `PATCH /api/team/{id}` — owner/admin; `{role}`; cannot change the owner or
  your own role.
- `DELETE /api/team/{id}` — owner/admin; soft-remove; cannot remove yourself.
- `POST /api/team/accept` — authenticated invitee; `{token}`.
- `/api/auth/me` now includes `role`, `workspace_owner_id`, `account_email`,
  `is_workspace_member`.

### Tests
Invite -> accept -> member sees the owner's leads and cannot see another
workspace; viewer write gate (403) with reads still allowed; agent config
gate; owner/admin-only team management; self-role and self-remove refusal;
cross-workspace 404/403; invite of an account that already owns leads -> 409;
wrong-email acceptance -> 403; unauthenticated 401.

## Module 2 scope — white-label v1 (shipped)
`ClientSettings` additions (`brand_name`, `logo_url`, `primary_color`,
`support_email`, `footer_text`, `hide_platform_brand`) + GET/PATCH wiring in
`/api/settings` (owner/admin/manager only) + rendering on the dashboard shell,
login screen and `/l/<slug>`. Honest scope: this is presentation only; it
does not create a separate tenant, custom domain, or remove the platform's
legal footer text when a plan requires it.

## Module 3 scope — manual billing ledger v1 (shipped)
New `billing_entries` table: `user_id, plan_tier, amount, currency,
period_start, period_end, paid_until, note, created_at`, entered by
owner/admin. `GET/POST/DELETE /api/billing` + a Settings card. Labels state
"manually recorded — no payment is processed here". `users.plan_tier` stays
the single source of truth for feature gating; the ledger is a record, not a
charge.

## Module 4 — agency multi-workspace (design only, needs approval)
Outline of the migration: introduce `workspaces` (id, name, owner_account_id,
plan_tier) and `workspace_members(workspace_id, account_id, role)`; add
`workspace_id` to every data table (leads, settings, campaigns, ...); backfill
one workspace per existing `User`, then swap `user.id` scoping for
`workspace_id`. Estimated effort: multi-session, with a dual-write/backfill
window and an audit pass. **Not started without explicit approval.**

## Ground rules for every P3 module
- No payment processing, no card storage, no auto-charge.
- No custom domains / DNS until hosting cost is approved.
- Tenant isolation stays enforced server-side; UI hiding is never the gate.
- Every "plan/limit" label must say it is manual, not enforced by a billing
  system, unless enforcement actually exists.
