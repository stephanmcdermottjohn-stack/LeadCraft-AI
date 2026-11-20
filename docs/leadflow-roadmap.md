# AI LeadFlow — Enhancement Roadmap & Competitive Intelligence Report

Baseline: LeadCraft AI (FastAPI + SQLAlchemy 2 + React/Vite + Supabase Postgres, live on Vercel).
Principle: **enhancement only** — every item below reuses the existing auth, tenant-scoping, migration, testing and deploy infrastructure.

---

## 1. Existing Feature Inventory (audited 2026-11-17)

**Backend:** FastAPI app factory + lifespan scheduler; JWT (HMAC) auth with PBKDF2; 18 routes across 8 routers (health, auth, admin, content, leads, public, settings); 7 tables (users, clients_settings, leads, lead_notes, content_posts, conversations, messages); Gemini LLM adapter (mock/gemini, 503 retry); lazy due-post worker pass for serverless; CSV export; streaming SQLAlchemy queries.

**Live routes:**
- Auth: register / login / me (`is_admin` on users; admin guard via `require_admin`)
- Leads: capture (public, consent-first, honeypot, template extras whitelist), import (Meta/Google CSV exports), list (`q`/`status`/`source` filters), export.csv, notes GET/POST, status PATCH
- Public: landing config (`extra_fields` per business template)
- Settings: GET/PATCH (niche, area, voice, slug, `show_property_fields`, `business_type` — 18 templates)
- Content: generate (mock/gemini), schedule, posts list (lazy due-pass)
- Admin: overview (aggregate stats, admin-only)

**Frontend:** SPA dashboard (Dashboard/Content/Leads/Conversations placeholder/Settings/Admin), public landing `/l/<slug>` with dynamic template extras, CSV import UI, notes UI, admin stats panel.

**Status by roadmap area:**

| Area | Status | Notes |
|---|---|---|
| A. Lead lifecycle | 🟡 Partial | CRM status enum + notes exist; no lifecycle stages, stage history, assignment, attribution or next-action |
| B. ICP builder | 🔴 Missing | Business templates exist but drive only landing-form extras |
| C. BANT | 🔴 Missing | Nothing |
| D. Score vs Grade | 🟡 Partial | `leads.score` column exists (always 0, unused); no grade, history, weights |
| E. Conversation inbox | 🟡 Skeleton | `conversations`/`messages` tables exist; no API, no UI |
| F. Visitor intelligence | 🟡 Partial | Landing conversion tracking only (lead capture); no sessions/events analytics |
| G. Landing/form builder | 🟡 Partial | One auto landing per business, 18 industry templates, consent+honeypot+thank-you; no custom pages, blocks, variants, A/B |
| H. Nurture engine | 🟡 Partial | Content scheduler infra reusable; no drip campaigns, no suppression list |
| I. Voice/telephony | 🔴 Missing | P2 design-only (see cost section) |
| J. Reputation/referral | 🔴 Missing | Nothing |
| K. Revenue attribution | 🟡 Partial | Source/status counts in admin; no revenue fields, no cost/ROI data |

---

## 2. Competitive Feature Gap Analysis

| Product | Concept worth taking | What we already have | Gap → Phase |
|---|---|---|---|
| **Salesforce** | BANT qualification, score vs grade separation, transparent scoring, conversion-outcome recalibration | Lead table with score column; status funnel | **P0** (B/C/D) |
| **GoHighLevel** | Lifecycle pipeline, nurture automations, retention/reactivation campaigns | Lead CRM base, scheduler worker, consent-first design | **P0** (A) + **P1** (H) |
| **Leadfeeder** | Visitor intent, ICP matching, CRM sync | Landing page analytics surface (submissions only) | **P0** (B) + **P2** (F provider) |
| **CallHippo** | AI voice agents, call summaries/analytics | LLM adapter (voice-ready abstraction) | **P2** design-only |
| All | Tenant isolation, audit, consent | Already core to the codebase | Maintain |

**Deliberately not copied:** proprietary code/branding; "identify every visitor" claims; IP→person inference; auto-outbound messaging without consent.

---

## 3. Prioritized Implementation Plan

### P0 — Core Intelligence (this approval cycle)
1. **Lead lifecycle engine** — `lifecycle_stage` on leads (capture→qualify→nurture→convert→retain→reactivate), `lead_stage_history` (from/to/timestamp/note), next-recommended-action, stage transitions validated; standard status enum untouched (reporting stays stable).
2. **Source attribution** — `campaign`, `utm_source/medium/content/term`, `landing_variant` columns on leads; capture/import/landing-query passthrough; attribution surfaced in list/CSV/admin.
3. **ICP builder** — `icp_profiles` (industry, size, location, budget range, needs, timeline, decision authority, custom criteria JSON) + 8 industry templates; rule-based fit check with per-factor explanation.
4. **BANT qualification** — `lead_qualifications` (budget/authority/need/timing: value, confidence known|unknown, source manual|ai); "unknown" is a first-class answer; no invented values.
5. **Scoring + grading (independent)** — engagement/activity scoring with configurable weights (heuristic, labeled as such); grade = ICP fit (A–D); `lead_score_history`; explanation endpoint; recalibration hook using converted outcomes.
6. **Activity timeline** — unified per-lead timeline (notes + status changes + stage changes + qualification edits).

### P1 — Conversion & Engagement (next cycle)
Landing-page/form builder (block-based, variants, A/B on headline/CTA/length reporting submissions + qualified leads), nurture workflows (consent-gated, suppression list, delivery metrics), unified inbox v1 (existing tables; WhatsApp/website-chat first), website analytics (first-party sessions/events, cookie-consent aware), funnel + campaign reports (distinguishing actual vs missing data).

### P2 — Advanced Intelligence (design first, then approve)
B2B visitor identification via a vetted provider (optional, off by default); voice module design (CallHippo-inspired) pending a telephony provider evaluation incl. Pakistan number/regulatory verification; review/referral workflows; advanced attribution.

### P3 — Commercial Scale
Agency workspaces, white-label, billing, enterprise permissions. Plan:
`docs/p3-plan.md`. Shipped: **team members & roles v1** (`workspace_members`,
owner-scoped membership resolution, viewer/agent write gates, token invites
with no email sending), **white-label branding v1** (brand name/logo/colour/
footer/support email, platform-brand toggle on the dashboard and landing
page), and **manual billing ledger v1** (owner/admin-recorded payments,
currency-grouped totals, plan label — no gateway, no enforcement). Agency
multi-workspace remains design-only until approved (requires a `workspace_id`
migration across all data tables).

---

## 4. Architecture Impact

- **Additive only.** No existing route/table changes break: `leads.status` (CRM funnel) and `lifecycle_stage` are separate concepts; standard reporting keeps using status.
- New service modules under `app/services/`: `lifecycle.py`, `icp.py`, `qualification.py`, `scoring.py` — pure functions, unit-testable, no network.
- Optional AI calls (BANT extraction, nurture copy) go through the existing `llm.py` adapter — provider stays swappable, mock provider keeps tests offline.
- Frontend: Lead detail panel grows tabs (Timeline / Qualification / Fit); Settings grows ICP editor; nav unchanged.
- Deploy: same two-project Vercel pipeline; migrations follow the existing idempotent `scripts/add_*.py` pattern.

## 5. Database Impact (P0)

New tables (all user-scoped, indexed on `(user_id)` + FKs):
- `lead_stage_history` — lead_id, user_id, from_stage, to_stage, note, changed_at
- `icp_profiles` — user_id, name, industry, company_size, location, budget_min/max, business_type, needs, timeline, authority, criteria_json, is_default
- `lead_qualifications` — lead_id, user_id, budget/authority/need/timing (each: value, confidence, source, updated_by, updated_at)
- `lead_score_history` — lead_id, user_id, score, grade, reason_json, created_at
- `lead_activities` — lead_id, user_id, kind, detail_json, created_at (unified timeline)

New columns on `leads`: `lifecycle_stage`, `grade`, `campaign`, `utm_source`, `utm_medium`, `utm_content`, `utm_term`, `next_action`, `next_action_at`.
New columns on `clients_settings`: `scoring_weights_json`, `lifecycle_config_json` (optional overrides; defaults keep standard reporting).

Data-retention rule: history tables append-only; deletion cascades with lead.

## 6. Estimated Implementation Effort (single dev + agent)

| Item | Effort |
|---|---|
| Lifecycle engine + history + next action | 0.5 session |
| Attribution columns + passthrough | 0.25 session |
| ICP builder + templates + matching | 0.5 session |
| BANT (manual + unknown-first) | 0.5 session |
| Score + grade + history + explanations | 0.5 session |
| Timeline endpoint + frontend panels | 0.5 session |
| Tests (target 46 → ~75) | included |
| **P0 total** | **~3 working sessions** |
| P1 total | ~5–7 sessions |
| P2 | provider-dependent |

## 7. External API / Provider Cost Assessment

- **P0: zero external cost.** Everything rule-based; optional BANT AI extraction uses the existing Gemini free tier (already configured). No new credentials.
- **P1: zero required cost.** First-party analytics on existing Supabase; nurture uses DB + scheduler. Email delivery, if added, would need a provider (Brevo/Mailgun free tiers ~100–300/day) — decision deferred with cost-benefit note.
- **P2: paid, opt-in only.** Visitor identification providers (Leadfeeder/Albacross-class, free tiers are site-count limited); telephony (Twilio-class, per-minute + number rental) — **requires explicit cost-benefit approval + Pakistan number/regulatory verification before any integration**. Voice stays design-only until then.
- Rule honored: paid providers are never required for core app function.

## 8. Security & Compliance Risks (P0-relevant)

| Risk | Mitigation |
|---|---|
| Cross-tenant leakage on new endpoints | Every new route scopes by `user_id` (existing pattern + tests assert 404/403) |
| Admin overreach | Admin endpoints stay aggregate-only (already enforced) |
| Score presented as "validated probability" | UI/API labels: "heuristic score — not a calibrated probability" until recalibration data exists |
| Invented BANT answers | `confidence=unknown` is the default; AI extraction only from consented conversation content, always marked `source=ai` and reviewable |
| ICP changes corrupting history | Grades snapshot into `lead_score_history`; historical rows never recomputed |
| Lifecycle misconfig | Custom stage config validated against the standard six; standard stage codes reserved |
| Attribution spoofing | UTM values length-capped + sanitized; server never trusts client timestamps |

---

## Acceptance criteria per module
Working frontend · backend API · migration · tenant-isolation checks · input validation · loading/empty/error states · automated tests · docs update (`docs/api-contracts.md`) · configuration notes · cost disclosure. Specific tests: stage transitions validate; BANT unknowns persist; score ≠ grade independence; ICP edits never rewrite history; tenant A never sees tenant B rows.
