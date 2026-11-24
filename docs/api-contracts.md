# Virtual Marketing & Lead Generation Platform — API Contracts (living doc)

Base URL (dev): `http://127.0.0.1:8000`

## GET /api/health
Liveness + integration configuration status. **Auth: none (liveness probe).**

Response 200:
```json
{
  "status": "ok",
  "app": "virtual-marketing-platform",
  "version": "0.1.0",
  "environment": "development",
  "integrations": {
    "anthropic_configured": false,
    "whatsapp_configured": false,
    "meta_webhook_configured": false,
    "meta_leadgen_configured": false
  }
}
```

## Live (security pass — auth & brute-force throttling)
Zero external cost. Counters live in `auth_throttles`, keyed by SHA-256 hashes only — no plaintext email address or IP is stored, and the table is excluded from ops export/usage.

- `POST /api/auth/register` — 201 with `{user, token}`; 409 when the email already exists; 422 for invalid input. **5 attempts per IP per hour → 429 + `Retry-After`** (duplicates count too, so bulk account creation and email enumeration are limited).
- `POST /api/auth/login` — 200 with `{user, token}`. An unknown email and a wrong password return the **same** `401 {"detail": "Invalid email or password."}`, and unknown emails still pay the full PBKDF2 cost (no timing oracle). **5 failures per email+IP in 15 min → 429 + `Retry-After`, locked 15 min**; **30 failures per IP in 15 min** locks that IP. A correct password while locked is still 429 — the limiter is checked first. A successful login clears the email+IP counter, while the IP-wide counter stays (one valid account cannot reset an attack counter). The 429 message never reveals whether the email exists.
- `GET /api/auth/me` — Bearer token required.
- Client IP resolution: `x-real-ip`, `x-vercel-forwarded-for`, then the left-most `x-forwarded-for`; falls back to the socket address (Vercel sets these headers).

## Live (P4 — integrations & real-time capture)
Zero external cost and disabled by default: webhook endpoints answer **503** until the server App Secret / verify token exist. Inbound only — no auto-reply, no outbound send.

- `GET /api/webhooks/meta` — Meta subscription handshake. 503 without `META_VERIFY_TOKEN`; 403 on token mismatch; else echoes `hub.challenge`.
- `POST /api/webhooks/meta` — Meta Lead Ads delivery. Requires a valid `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with `META_APP_SECRET`); missing/invalid → 403, secret unset → 503. Parses `entry[].changes[]` where `field="leadgen"`, stores one `webhook_events` row per `leadgen_id` (unique key → retries are duplicates), routes by `clients_settings.meta_page_id`. Without `META_PAGE_ACCESS_TOKEN` the delivery stays `pending_credentials` (retry later); with it, Graph API `field_data` is mapped onto a lead: `source="meta_lead_ad"`, server-side `consent_timestamp`, `utm_source="meta"`, full answers in `metadata.answers`. Unknown page id → `unrouted`, `user_id=NULL` (no guessed tenant).
- `GET /api/webhooks/whatsapp` — same handshake contract.
- `POST /api/webhooks/whatsapp` — WhatsApp Cloud API delivery, same signature rules. Routes by `clients_settings.whatsapp_phone_number_id`; each inbound message is idempotent by WhatsApp message id. Text/button/interactive bodies are stored; media is labelled and never downloaded. Unknown sender creates one `source="whatsapp_inbound"` lead + conversation + inbound message; known sender reuses them. Status callbacks are acknowledged and ignored.
- `GET /api/settings` — now also returns `integrations: {meta_page_id, whatsapp_phone_number_id, meta_webhook_url, whatsapp_webhook_url, meta_verify_token_configured, meta_app_secret_configured, meta_page_access_token_configured, whatsapp_access_token_configured, meta_ready, whatsapp_ready, credentials_note, notes[]}`. Booleans only — secrets never reach the browser.
- `PATCH /api/settings` — accepts `meta_page_id` / `whatsapp_phone_number_id` (numeric, 5–64 digits; `""` clears). Owner/admin/manager only (existing role gate).
- `GET /api/integrations/events?source=&status=&limit=` — auth, **owner/admin** (payloads contain contact details; agent/viewer → 403). Workspace-scoped; `include_unrouted=true` is platform-admin only and reveals `user_id=NULL` rows.
- `GET /api/integrations/events/{id}` — owner/admin, tenant-404; includes the stored `payload`.
- `POST /api/integrations/events/{id}/retry` — owner/admin, tenant-404. Retryable statuses: `unrouted`, `pending_credentials`, `error`, `received`; `processed`/`ignored` → 400. Re-runs routing and (for leadgen) the Graph fetch, never duplicating a lead because the event key is unique.

## Planned (defined now, implemented in later phases — do not call yet)
- `POST /api/leads/match` — area → registered dealers matching (Phase 3)

## Live (Phase 3 — landing page lead capture)
- `POST /api/leads/capture` — the ONLY public lead-write endpoint. Requires `slug` (business landing page), `name`, `consent: true`, and at least one of phone/email. `consent_timestamp` is recorded SERVER-SIDE. Honeypot `company` field silently rejects bots (400). `source` is fixed to `landing_page`. Optional property fields (only when the business enables `show_property_fields`): `deal_type` (buy/rent/sell), `property_type`, `budget` — stored in `metadata_json`. 201 → `{lead: {id, status}}`.
- `GET /api/public/landing/{slug}` — public, no-auth landing page config. Returns ONLY business display fields (business_name, niche, target_area, show_property_fields). Never personal data or other clients' rows. 404 for unknown slugs.
- `GET /api/leads?q=&status=&source=` — auth. The owner's leads, newest first (max 200). Filters: `q` (ilike over name/phone/email/area/intent_notes), `status` ∈ {new, contacted, converted, archived}, `source` ∈ allowlist; invalid values → 400. Each row carries `source`, `consent_timestamp`, `status`, `metadata` (parsed dict).
- `GET /api/leads/export.csv` — auth. Streaming CSV download (user-scoped, max 5000 rows). Columns: id, created_at, source, status, name, phone, email, area, deal_type, property_type, budget, intent_notes, consent_timestamp. `Content-Disposition: attachment; filename="leads-<date>.csv"`.
- `GET /api/leads/{id}/notes` — auth. The lead's notes, newest first. Other users' leads → 404.
- `POST /api/leads/{id}/notes` — auth, 201. Body `{body: string}` 1–2000 chars; whitespace-only → 422. Append-only (no edit/delete in MVP). Other users' leads → 404.
- `PATCH /api/leads/{id}/status` — auth. Status ∈ {new, contacted, converted, archived}; other users' leads → 404.
- `GET /api/settings` / `PATCH /api/settings` — auth. Now includes `landing_slug`, `show_property_fields`, and `business_type` (Phase 3D template key: property, ecommerce, hospitality, restaurant, salon, health, education, fitness, travel, auto, construction, legal, events, photography, cleaning, finance, it, or ""). PATCH semantics: omitted field = keep existing; `show_property_fields` is a boolean; `landing_slug: "auto"` derives a slug from the business name (suffix -2, -3… on conflicts); explicit slug validated (`^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$`, reserved words rejected) and globally unique (409 on conflict); unknown `business_type` → 400.
- `POST /api/leads/import` — auth, 201. Manual platform-export import (Meta Lead Ads / Google lead form CSV) while the automated webhook is pending. Body: `{source: "meta_lead_ad"|"google_lead_form", consent: true, rows: [{name, phone, email, area, notes}]}` (max 500 rows). Rows without a name or any contact are skipped (reported, not fatal). `consent_timestamp` stamped server-side; the consent flag is the importer's attestation that leads opted in on the source platform. Other sources → 400.
- `GET /api/admin/overview` — auth, **admin only** (403 otherwise). Aggregate platform stats: total users, total leads, leads by status/source, 20 most recent businesses with lead counts. Admins never see another business's individual lead rows (privacy rule). Promote via `python scripts/make_admin.py <email> <password>`.
- Landing page URL: `/l/<slug>` (frontend SPA route); shows the business template's `extra_fields` (generic key/label/type form controls served in the config) when the business enables the toggle.

## Live (AI LeadFlow P0 #1 — lifecycle stages + attribution)
- Lifecycle `stage` is a SEPARATE axis from CRM `status` (new/contacted/converted/archived). Stages ∈ {capture, qualify, nurture, convert, retain, reactivate}. Every stage change appends to `lead_stage_history` (append-only, never rewritten). Bridge rule: `status=converted` auto-moves stage to `convert` (logged in history); the reverse never happens automatically.
- `PATCH /api/leads/{id}/stage` — auth, tenant-404. Body `{stage}` from the allowlist; invalid → 400.
- `GET /api/leads/{id}/stage-history` — auth, tenant-404. Newest-first `[{stage, changed_at, from_crm_status?}]`.
- Lead list rows now also carry `stage`, `grade`, `assigned_to`, `next_action`, `next_action_at`, `campaign`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `landing_url`.
- Capture attribution: `/api/leads/capture` and `/api/leads/import` read `landing_url` + `utm_*` from the body (and fall back to nested `extra`) and store them on the lead. Landing page passes URL params through automatically.

## Live (AI LeadFlow P0 #2 — ICP builder + explainable fit)
- ICP profiles are user-scoped; cross-tenant reads/writes → 404. Fit is computed on demand — editing/deleting a profile never rewrites historical data.
- Fit model (rule-based, transparent): 4 factors — location 25, needs 35, services 25, budget 15. Status per factor ∈ {match, partial, no_match, unknown}. Score = earned ÷ evaluable × 100; **unknown factors never drag a lead down** (they narrow the basis). Grade bands: A ≥ 75, B ≥ 50, C ≥ 30, else D. No evaluable factor → `score: null, grade: ""` ("Not enough information"). Always presented as a heuristic grade, never a calibrated probability.
- `GET /api/icp/templates` — public. 8 keys: property, education, healthcare, ecommerce, recruitment, saas, professional_services, other.
- `GET /api/icp` — auth. Own profiles, newest first.
- `POST /api/icp` — auth, 201. Body: `{name (1–100, required), industry?, company_size?, location?, budget_min?/budget_max? (int, PKR), business_type? (validated key), needs?, preferred_services?, decision_authority?, buying_timeline?, criteria? (≤12 strings, extras dropped), is_default?}`. `budget_min > budget_max` → 400; unknown business_type → 400. `is_default: true` unsets the previous default.
- `PATCH /api/icp/{id}` / `DELETE /api/icp/{id}` — auth, tenant-404.
- `POST /api/icp/{id}/match/{lead_id}` — auth, tenant-404 either side. 200 → `{lead_id, profile_id, fit: {score, grade, factors: [{factor, status, detail, points, weight}]}}`. Budget parsing: first number in the lead's `metadata.budget` (accepts "150000", "1.5 crore", "80 lakh" — expanded to raw PKR, no currency conversion; the detail line states the comparison as-is).

## Live (AI LeadFlow P0 #3 — BANT qualification, unknown-first)
- One `lead_qualifications` row per lead, created lazily on first PATCH. Every dimension (budget / authority / need / timing) carries `{value, confidence: known|unknown, source: manual|ai}`. **Unknown is a first-class answer** — a value is only 'known' when explicitly recorded with its source; nothing is ever inferred or invented.
- `GET /api/leads/{id}/qualification` — auth, tenant-404. Returns `{qualification: {dimensions, complete: <0..4>, total: 4, suggestion, updated_at}}`; leads without a row get the all-unknown shape (and NO row is created by reading).
- `PATCH /api/leads/{id}/qualification` — auth, tenant-404. Body: any subset `{budget?, authority?, need?, timing?}` as free text ≤500 chars (whitespace/empty resets that dimension to unknown; >500 → 422; empty body → 400). Source stamps `manual` (AI-sourced edits arrive later via their own path). `complete` honestly reports N of 4 known.
- `suggestion` guidance: 0 known → "" (unknown-first); partial → "Still unknown: <dims> - ask on the next contact."; all 4 → "BANT complete - if the lead is a good ICP fit, move it to nurture with a follow-up plan." (mirrors the lifecycle default next-action wording; no state is forced).
- Frontend: inline BANT editor per lead card (per-dimension known/unknown labels, blank = unknown, completeness badge `BANT (n/4 known)`).

## Live (AI LeadFlow P0 #5 — engagement scoring + grade snapshotting)
- **Score ≠ grade.** Score = heuristic engagement number (labeled "heuristic engagement score — not a calibrated probability"); grade = ICP-fit snapshot (A–D, "" when nothing evaluable). Each `POST score` appends a snapshot; history rows are never recomputed — ICP edits or weight changes cannot rewrite the past.
- Weights (`clients_settings.scoring_weights_json`, defaults shown; user-editable via `PATCH /api/settings` `scoring_weights` — unknown keys dropped, values clamped 0..100, no 422):
  - `consent_base: 10` — every consented lead starts here
  - `per_note: 3` — per follow-up note, first 5 counted (max 15)
  - `per_bant_known: 5` — per known BANT dimension (max 20); unknown dims earn nothing, never penalized
  - `budget_stated: 10` — lead gave a parseable budget in template extras
  - stage: `capture: 0`, `qualify: 5`, `nurture: 10`, `convert: 15`, `retain: 15`, `reactivate: 5`
- `POST /api/leads/{id}/score` — auth, tenant-404. Optional body `{weights: {...}}` for a one-off override (stored settings unchanged). Returns `{score, grade, label, factors: [{signal, points, weight, detail}], weights_used, history_count}`; also updates `leads.score`/`leads.grade` to the latest snapshot. Empty body allowed.
- `GET /api/leads/{id}/score-history` — auth, tenant-404. Newest-first snapshots `{id, score, grade, reason: {label, weights, factors}, created_at}`.
- `GET /api/scoring/feedback` — auth. Recalibration hook: `{converted_count, avg_score_converted, avg_score_other, ready_for_recalibration, note}`. Honest: below 5 converted leads with snapshots it explicitly says no recalibration is suggested; even when ready, recalibration stays a human decision (no auto weight changes).
- Frontend: "⚡ Score lead" button per card with inline factor breakdown + snapshot count.

## Live (AI LeadFlow P0 #6 — unified activity timeline)
- `GET /api/leads/{id}/timeline` — auth, tenant-404. Read-only merge of the append-only sources, newest first: `lead_notes` (type `note`), `lead_stage_history` (type `stage`, includes the original capture row), `lead_activities` (type = kind: `status_changed`, `qualification_updated`). Each event: `{type, text, at}`. The endpoint fabricates nothing and rewrites nothing.
- `lead_activities` records timeline events that live outside dedicated tables — CRM status changes (real changes only; setting the same status twice logs nothing) and BANT edits (`BANT updated: <dim>=<value>, ...`). Written by `PATCH /api/leads/{id}/status` and `PATCH /api/leads/{id}/qualification`.
- Frontend: "Timeline" toggle per lead card with per-type color coding.

## Live (P1 #1 — landing page A/B variants)
- Variants override **headline / subtext / CTA label** only (blank = inherit business defaults); page structure, consent form, honeypot stay unchanged. The "control" arm is the business defaults (no row). Max 5 variants.
- `GET /api/landing-variants` / `POST` (201) / `PATCH /{id}` / `DELETE /{id}` — auth, tenant-404. Label: 1–50 chars `[A-Za-z0-9-]`, case-insensitively unique (409), **fixed after creation** (rename refused — it would orphan past traffic), never `control`. Inactive variants keep their historical numbers.
- `GET /api/public/landing/{slug}` — now assigns an A/B arm: `?variant=` re-serves a specific arm (frontend remembers the visitor's arm in **localStorage `lc_ab_<slug>`, no cookies**); omitted → uniform random among active arms. Response adds `ab_variant: "control"|"<label>"` and `variant: {label, headline, subtext, cta_label} | null`. Unknown arm → 404.
- `POST /api/public/landing/{slug}/impression` — no-auth, no PII, 204; counts an impression for the stated arm (unknown labels count as control; unknown slugs are silently ignored, no row). One row per page view in `landing_events`.
- Submissions and qualified leads are NOT double-tracked: computed from `leads.landing_variant` (capture continues to accept it; the landing page now sends the assigned arm automatically).
- `GET /api/landing-variants/report` — auth. Per arm: `{impressions, submissions, qualified, submission_rate_pct, note}`. Honest missing-data rules: 0 traffic → rate `null` + "conversion rate unknown (not 0%)"; < 30 impressions → rate `null` + "too early to compare arms". `qualified` = lead left `capture` stage OR has a score snapshot.

## Live (P1 #2 — nurture workflows v1)
- **Honest scope: nothing is auto-sent.** A due touch surfaces as the lead's `next_action` (+ `next_action_at`) and a `nurture` timeline activity — the owner executes the touch. Zero external cost; email/SMS delivery stays deferred.
- Consent gate: enrollment requires the lead's recorded `consent_timestamp`; a contact on the user's suppression list enrolls as `suppressed` (never active). One enrollment per (campaign, lead) — duplicate → 409.
- `GET/POST /api/nurture/campaigns`, `PATCH/DELETE /api/nurture/campaigns/{id}` — auth, tenant-404. Steps: 1–8 × `{day_offset: 0–365, message: 1–500}`; invalid → 400. Inactive campaigns refuse enrollment (400). Delete blocked while ANY enrollment exists (any status — history integrity); deactivate instead.
- `POST /api/nurture/campaigns/{id}/enroll` `{lead_id}` → 201 `{enrollment, outcome: active|suppressed}`. `GET /api/nurture/enrollments?campaign_id=` lists with lead names. `POST /api/nurture/enrollments/{id}/stop` → `stopped` (+ activity).
- Step timing: step *i* is due at `enrolled_at + steps[i].day_offset` (UTC). `POST /api/nurture/process-due` surfaces every already-passed step in order (catch-up), advances `current_step`, sets the lead's next action, logs activities, and completes the sequence after the last step. The scheduler worker runs the same pass globally every 60s.
- `GET/POST /api/nurture/suppressions`, `DELETE /{id}` — per-user do-not-nurture list by phone or email (normalized, duplicate → 409). Enrollment-time matching: phone (spaces stripped) or email.
- `GET /api/nurture/campaigns` includes per-campaign `metrics` (`enrolled_total`, `active`, `completed`, `stopped`, `suppressed`, `touches_surfaced` + honest note).
- Frontend: Settings "Nurture campaigns" editor (steps rows: day + message); per-lead "Nurture" panel (choose campaign → Enroll, enrollment status, Stop, "Check due" runs the pass on demand).

## Live (P1 #3 — unified inbox v1)
- **Consent-first gate is enforced in the API, not just the UI.** Recording an inbound message is always allowed; an **outbound** message is refused (400, "Outbound-first contact is not allowed - record the lead's inbound message first.") until that conversation has at least one `direction=in` message.
- Channels allowlist: `whatsapp_inbound | website_chat | direct_message`. Unknown → 400. Conversation creation also requires the lead's `consent_timestamp` (400 otherwise) and is tenant-checked (404). `POST /api/inbox/conversations` `{lead_id, channel}`.
- `GET /api/inbox/conversations` — auth. Own-tenant conversations, newest activity first; per row: `{id, lead_id, lead_name, lead_phone, channel, last_message_at, last_message_preview (≤120 chars), last_direction, has_inbound}`.
- `GET /api/inbox/conversations/{id}/messages` — auth, tenant-404. `{conversation, messages: [{id, direction, body, sent_at}]}` oldest first.
- `POST /api/inbox/conversations/{id}/messages` `{direction: in|out, body: 1–2000}` → 201. Whitespace-only body → 422; other direction → 400. The platform only **records** messages: the owner sends from their own WhatsApp/phone (no provider is wired — zero external cost). No auto-bot in v1.
- Timeline merge: every message also appears in `GET /api/leads/{id}/timeline` as `{type: "message", text: "[channel] → them: …" (out) / "← them: …" (in)}`.
- Frontend: "Conversations" nav is now the real inbox — left list (channel badge, direction arrow + preview), "+ New" (lead + channel), thread view, "← Log inbound" / "Reply →" (reply disabled with an explanation until the lead has spoken).

## Live (P1 #4 — website analytics v1)
- First-party, **cookie-free, PII-free** events. The landing page creates an opaque session id in `sessionStorage` (`lc_sid` — gone when the tab closes) and posts `page_view` / `form_start` / `submit`. Stored: event name, path (query string stripped), referrer **host only** — no IPs, user agents or full URLs.
- `POST /api/public/landing/{slug}/events` `{session_id, event, path?, referrer?}` → 204 always. Malformed payloads (session id must be 8–64 `[A-Za-z0-9_-]`, event must be in the allowlist) and unknown slugs are silently ignored — no probing, never breaks the landing page.
- `GET /api/analytics/summary?days=1..365` — auth, tenant-scoped. Returns `events_total`, `sessions_total`, `event_counts`, `funnel` (unique sessions: page_view / form_start / submit), `form_start_rate_pct`, `submit_rate_pct`, `leads_captured` (server-side, authoritative), `daily` (last ≤14 days), `rates_known`, `notes`.
- Honest rules: rates are `null` (never 0%) when there are no sessions, and stay `null` until **30+ unique sessions** in the window ("too early to judge rates"). If client-side `submit` events exceed server-side lead captures, a note says captures are authoritative (client retries can repeat). A permanent note discloses that ad blockers / JS-disabled visitors may be missing.
- Frontend: Dashboard "Website analytics" card (7/30/90-day window, sessions/page views/form starts/leads, funnel bars, rates or "unknown", honest notes). Landing page tracks `page_view` on load, `form_start` on first form focus, `submit` after a successful capture.

## Live (P1 #5 — funnel + campaign reports v1)
- `GET /api/reports/funnel?days=1..365` — auth, tenant-scoped. Window = leads **created** in the last N days (older leads excluded; stated in `notes`).
- `funnel[]`: per stage (`capture…reactivate`) `reached` (distinct leads from the append-only `lead_stage_history` — ever recorded in that stage), `current` (snapshot of `lifecycle_stage`), `reached_rate_pct`. Leads with no history rows at all fall back to their current stage. Honest note: stage order is **not enforced** by the API, so a lead can skip or move back — the funnel does not pretend to be monotonic.
- `sources[]`, `campaigns[]`, `utm_sources[]`: `{key, total, qualified, converted, qualified_rate_pct, converted_rate_pct}` sorted by volume. Missing attribution is grouped as `(unattributed)` — never guessed.
- Definitions: **qualified** = left the `capture` stage OR has a score snapshot; **converted** = `convert/retain/reactivate` stage OR CRM `status=converted`.
- Honest rate gates: rates are `null` (unknown, not 0%) with zero leads, and all rates stay `null` below **10 leads** in the window ("too early"). `rates_known` states which case applies.
- Frontend: "Reports" nav — window selector (7/30/90), lead/qualified/converted summary, reached-vs-current funnel bars, source/campaign/UTM tables, and the explicit missing-data notes.

## Live (P2 #1 — reviews & referrals v1)
- **Reviews** (`review_requests`): `GET/POST /api/reviews`, `PATCH /api/reviews/{id}` — auth, tenant-404. Gates: lead must have `consent_timestamp` **and** be converted (`lifecycle_stage in convert/retain/reactivate` OR CRM `status=converted`); any other lead → 400. One **open** request per lead (duplicate → 400); re-request allowed after completed/declined. `requested → completed|declined` only (double-resolve → 400).
- **The platform never sends review asks.** `requested` logs the owner's own ask; outcomes are manual. No rating/review text is stored or displayed (no fabricated social proof). Each change writes a `review` timeline activity.
- Review summary: `total`, `requested`, `completed`, `declined`, `by_channel`, `completion_rate_pct` (`null` with zero asks, never 0%), plus a small-sample note below 10 requests.
- **Referrals:** `POST /api/referrals/leads/{id}/code` returns a random per-business code + share path `/l/<slug>?ref=<code>` (stable on repeat). Capture accepts `referral_code`; the new lead gets `referred_by_lead_id` (same-tenant FK, capture-time only → no cycles). Unknown or cross-tenant codes are **silently ignored** — the public form never reveals code existence.
- `GET /api/referrals/report?days=1..3650` — auth, tenant-scoped: per-referrer referrals/qualified/converted + totals. `rates_known` false below 10 referred leads → rates `null` ("too early", never 0%). Only link-based referrals are measured; manual word-of-mouth is explicitly outside the numbers.
- Leads API now returns `referred_by_lead_id`; landing page passes `?ref=` through as `referral_code`.
- Frontend: per-lead "Review" (converted leads only; log ask / mark completed / declined) and "Refer" (generates + copies the share link); Reports adds Reviews and Referrals cards.

## Live (P2 #2 — advanced attribution v1)
- `GET /api/attribution/report?days=1..3650` — auth, tenant-scoped. **Capture-time attribution only**: one campaign/UTM set per lead, no multi-touch modelling (stated in `notes`).
- `coverage`: `leads`, `campaign_tagged`, `utm_tagged`, `any_tagged` + percentages (`null`, never 0%, when there are no leads). Missing tags are reported, never inferred.
- `campaigns[]`: `leads/qualified/converted`, rates (gated: `null` below 10 leads), owner-entered `spend`/`currency`, and `cost_per_lead` / `cost_per_qualified` / `cost_per_conversion` (`null` until spend is set — never invented). Spend rows with zero leads still surface. `utm_sources[]` for source-level counts (spend is campaign-level only).
- `median_time_to_qualify_days` / `median_time_to_convert_days` from platform timestamps only (lead `created_at` → first qualifying stage-history row), with sample counts and an explicit "unknown" note when no samples. Never backdated or estimated.
- **No ROI**: revenue is not tracked anywhere, so the report says so instead of computing a fake return.
- Spend registry: `GET /api/campaign-spend`, `PUT /api/campaign-spend` (upsert per campaign; `spend >= 0`, empty name → 400/422), `DELETE /api/campaign-spend/{id}` (tenant-404). One row per `(user, campaign)`.
- Frontend: Reports "Attribution & spend" card — coverage, medians, per-campaign table with inline spend entry + Save, cost ratios, honest notes.

## Live (P3 #1 — team members & roles v1)
Tenancy is unchanged: `User` is still the workspace. An **active** membership is resolved to the owner account inside `get_current_user`, so all existing `user.id` routes read/write workspace data with no schema change. Roles: `owner` (implicit), `admin`, `manager`, `agent`, `viewer`.

- **Write gates (server-side, 403):** `viewer` is read-only for every non-GET request except `/api/auth/*`. `agent` cannot change business configuration: `PATCH /api/settings`, `/api/landing-ab/*`, `/api/campaign-spend`. Team routes require owner/admin.
- `GET /api/team` — auth, workspace-scoped. Returns `workspace` (owner id, business name, plan tier), `my_role`, the implicit owner row, and `members[]` (`email`, `role`, `status` invited|active|removed, timestamps). `invite_path` (single-use token) is returned only to owner/admin.
- `POST /api/team/invite` — owner/admin, 201. Body `{email, role}`; role ∈ admin|manager|agent|viewer (owner rejected). **No email is sent** — the response carries the invite path to share manually. Re-invite rotates the token. 409 when the email already belongs to an account **with its own leads** (never silently re-scope someone's workspace) or is already active here/elsewhere.
- `POST /api/team/accept` — authenticated invitee, body `{token}`. Single-use; the account email must match the invited email (403 otherwise); token must be pending/valid (404); 409 when the account already owns leads or is active in another workspace. Removal falls back to the member's own (empty) personal workspace.
- `PATCH /api/team/{id}` — owner/admin, `{role}`; 400 when changing your own role or a removed member; cross-workspace ids → 404.
- `DELETE /api/team/{id}` — owner/admin, 204, soft-remove (`status=removed`); self-removal refused (400); cross-workspace → 404.
- `/api/auth/me` (and login/register) now include `role`, `workspace_owner_id`, `workspace_owner_email`, `is_workspace_member`. `email` remains the logged-in identity while `business_name` and data belong to the workspace.
- **Honest scope:** team seats are manually managed (no billing enforcement), no email delivery, one workspace per person in v1, and no ownership transfer / workspace deletion yet.

## Live (P3 #2 — white-label branding v1)
Presentation only: no custom domain, no separate tenant, no plan enforcement (stated in the API payload and UI).

- `PATCH /api/settings` accepts `brand_name` (≤200), `logo_url` (≤500), `primary_color`, `support_email` (≤320), `footer_text` (≤300), `hide_platform_brand`. Owner/admin/manager only (agents/viewers cannot write settings).
- Validation: `primary_color` must be `#RRGGBB` (stored lowercase) or empty; `logo_url` must be absolute `http(s)://` or a `/`-relative path with no whitespace (blocks `javascript:`/`data:`); `support_email` must look like an email; empty string clears a field.
- `GET /api/settings` returns the branding fields plus `white_label_note` (scope disclaimer).
- `GET /api/public/landing/{slug}` now also returns `brand_name`, `logo_url`, `primary_color`, `support_email`, `footer_text`, `hide_platform_brand` — display fields only, still no owner personal data.
- Frontend: landing page shows logo/brand name (fallback: business name), accent button colour, support email, custom footer; `hide_platform_brand` removes the "Powered by LeadCraft AI" footer. Dashboard sidebar uses the brand name/logo and accent colour; when hidden it falls back to the business name. Login screen is pre-auth and therefore not branded (stated honestly).

## Live (P3 #3 — manual billing ledger v1)
**No payment processing exists.** Rows record what the owner/admin says was paid; no card data, no gateway, no auto-charge, no enforcement.

- Role gate: all `/api/billing` routes require **owner or admin** (agents and viewers → 403; viewers are blocked even for reads because amounts are financial).
- `GET /api/billing` — `plan_tier`, `plan_tiers` (basic|pro|agency), `entries[]`, `entry_count`, `totals_by_currency` (summed **per currency**, never converted), `latest_paid_until`, and three honesty notes.
- `POST /api/billing` — `{amount>0, currency (2–10, uppercased, default PKR), period_start?, period_end?, paid_until?, note?}`; 400 on `amount<=0`, unknown/short currency, or `period_end < period_start`. 201 returns the entry.
- `PATCH /api/billing/plan` — `{plan_tier}` ∈ basic|pro|agency; updates `users.plan_tier` (the single plan field) and returns "no charge / no limits enforced". It never creates a ledger row.
- `DELETE /api/billing/{id}` — owner/admin, tenant-scoped 404, 204.
- Frontend: Settings "Billing ledger (manual)" card — plan label selector, entries table with delete, add-payment form (amount/currency/dates/note), grouped totals, honest disclaimers. Non-owner/admin sees an "owner or admin role required" notice.

## Live (P5 #1 — booking & appointments v1)
Zero external cost. **The platform sends no SMS, email or WhatsApp confirmation/reminder**; `reminded_at` is a manual marker set by the owner. Full scope: `docs/p5-plan.md`.

- `GET /api/appointments/availability` — auth, workspace-scoped. Returns `availability` (`enabled`, `days` 0=Mon…6=Sun, `start`/`end` `HH:MM`, `slot_minutes` 15–180, `lead_minutes`, `timezone` IANA, `services[]`, `note`, `max_days_ahead` 60, `disclaimer`) and `can_edit` (owner/admin/manager).
- `PATCH /api/appointments/availability` — **owner/admin/manager** (agent → 403). Validation: days 0–6; `HH:MM` start/end with `end > start`; slot 15–180; notice 0–10080; valid IANA timezone; ≤10 services; enabling with zero working days → 400.
- `GET /api/appointments/slots?date=YYYY-MM-DD` — auth, owner preview of the public slot list.
- `GET /api/appointments?status=&date_from=&date_to=&limit=` — auth, tenant-scoped, soonest first. Rows carry `starts_at`/`ends_at` (UTC ISO), `service`, `source` (`public_booking`|`manual`), `status` (`booked|confirmed|completed|cancelled|no_show`), `owner_notes`, `reminded_at`, and the linked lead's name/phone/email. Also returns `timezone` + honesty `note`.
- `POST /api/appointments` — auth, 201, manual (phone/walk-in) entry. Body `{starts_at (future), name, phone?, email?, service?, notes?, consent: true}`; missing consent or contact → 400, taken slot → 409. Creates/reuses a lead with `source="direct_message"`, `metadata.entry_point="manual_appointment"`, server-side `consent_timestamp`.
- `PATCH /api/appointments/{id}` — auth, tenant-404. `{status?, owner_notes?, reminded?}`; unknown status → 400; every status change appends a `LeadActivity`.
- `GET /api/public/landing/{slug}/slots?date=` — **public**. Server-generated slots only: booking disabled → `enabled:false` + empty list; closed weekday, past date, or beyond 60 days → empty; malformed date → 400; unknown slug → 404. Returns `services`, `slot_minutes`, `timezone`, and a hint that no message is sent by the platform.
- `POST /api/public/landing/{slug}/book` — **public**, 201. Body `{starts_at, name, phone?, email?, service?, intent_notes?, consent: true, company? (honeypot)}`. Consent required (400); at least one contact required; the time must be one of the server's current slots (forged/closed/too-soon → 409); same start already active → 409. New lead: `source="landing_page"`, `metadata.entry_point="booking"`, server-side `consent_timestamp`; repeat phone/email reuses the lead. Response includes the local label and the explicit "platform does not send confirmation or reminder messages" statement.
- `GET /api/public/landing/{slug}` now also returns `booking` (public availability subset — no owner data).
- Frontend: **Appointments** nav — availability editor, appointment table with status/reminder actions, manual add form; landing page offers a booking mode when enabled (date → slots → details/consent → confirmation).

## Live (P5 #2 — data, audit & ops v1)
Owner/admin only (agent/viewer → 403, unauth → 401). Zero external cost, no metering provider. Full scope: `docs/p5-ops-plan.md`.

- `GET /api/ops/export` — JSON attachment of the workspace's own data (profile, settings without secrets, leads, notes, stage history, activities, qualifications, scores, appointments, content, conversations/messages, reviews, campaign spend, nurture, billing ledger, team members without invite tokens, routed webhook deliveries). Capped at 5,000 rows per table (`truncated_tables`); anonymous telemetry and `password_hash` are excluded and stated in the payload. Logged as `ops.export`.
- `GET /api/ops/audit?action=&limit=1..500` — newest-first workspace audit entries (`actor_email`, `action`, `target_type`, `target_id`, safe `detail`), distinct `actions[]`, `append_only: true`. Recorded actions: `settings.updated` (keys only), `team.invited|joined|role_changed|removed`, `billing.entry_added|entry_deleted|plan_changed`, `booking.availability_updated`, `ops.export`, `ops.retention_purged`. Lead edits stay in the lead timeline.
- `GET /api/ops/retention/preview?days=30..3650` — counts of `landing_events`, `analytics_events`, and `processed|ignored` `webhook_events` older than the cutoff, plus what is kept.
- `POST /api/ops/retention/purge` — `{days (30–3650), confirm}`; `confirm` false → 400. Deletes only those telemetry rows; leads/consent/notes/appointments/audit log are never touched. Writes an audit row with deleted counts.
- `GET /api/ops/usage` — workspace row counts (leads, appointments, content, notes, conversations/messages, reviews, webhooks, telemetry, active team members) and last-activity timestamps. Explicitly rows, not storage bytes.
- Frontend: Settings → "Data, audit & ops" card (download JSON, usage grid, retention preview/purge, audit table, role notice for non-owner/admin).

## Live (P5 #3 — revenue & ROI tracking v1)
Owner/admin/manager only for money (agent/viewer → 403, unauth → 401). Manual entries, zero external cost, no currency conversion. Full scope: `docs/p5-revenue-plan.md`.

- `GET /api/leads/{lead_id}/outcome` — current `DealOutcome` (`open|won|lost`, `amount`, `currency`, `closed_at`, `note`) or `null`, plus `can_edit`. `404` for another workspace's lead.
- `PUT /api/leads/{lead_id}/outcome` — validate + upsert (one row per lead). `status` allowlist; `amount` finite 0–1e12; `currency` 2–10 letters normalised to uppercase; `closed_at` `YYYY-MM-DD`, forced `null` for `open`, defaults to today, never future. Invalid → `400`. Appends a `deal_outcome` activity to the lead timeline.
- `DELETE /api/leads/{lead_id}/outcome` — remove the row; revenue becomes unknown again. Appends `deal_outcome_cleared`. `404` if none.
- `GET /api/reports/revenue?days=1..3650` — `outcomes` (won/lost/closed/open, `win_rate_pct`, `rates_known`, `rate_gate=10`), `coverage` (leads with outcome / total), `totals_by_currency[]` (revenue, avg deal, open/lost value, spend, `roi_pct`, `cost_per_won`), `campaigns[]` (by lead campaign + currency, `(unattributed)` never guessed), and `notes[]` stating the rules. `roi_pct`/`cost_per_won` are `null` until spend exists in the same currency and at least one won deal is recorded (zero won deals = revenue unknown, never `-100%`); win rate `null` below 10 closed deals; currencies never mixed/converted; spend is all-time owner-entered while revenue is windowed.
- Ops: `deal_outcomes` included in `/api/ops/export` and `/api/ops/usage`.
- Frontend: Leads → per-lead "Deal" toggle (status/amount/currency/close date/note, save/remove, role-gated); Reports → "Revenue & ROI" card with per-currency + by-campaign tables and honest unknown labels.

## Ground rules encoded in contracts (Section 0 of the roadmap)
- Every lead write requires a `source` from the allowlist and a `consent_timestamp`.
- No endpoint creates outbound-first contact. `messages.direction=in` rows must exist before the bot replies.
