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
    "whatsapp_configured": false
  }
}
```

## Planned (defined now, implemented in later phases — do not call yet)
- `POST /api/webhooks/meta/leadgen` — Meta Lead Ads webhook; stores lead with `source=meta_lead_ad` + consent timestamp (Phase 3). Verify-token handshake per Meta docs before any real webhook goes live.
- `POST /api/leads/match` — area → registered dealers matching (Phase 3)
- `POST /api/webhooks/whatsapp` — WhatsApp Cloud API inbound; bot replies ONLY to opted-in/inbound contacts (Phase 4)

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

## Ground rules encoded in contracts (Section 0 of the roadmap)
- Every lead write requires a `source` from the allowlist and a `consent_timestamp`.
- No endpoint creates outbound-first contact. `messages.direction=in` rows must exist before the bot replies.
