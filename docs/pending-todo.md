# Pending work & go-live to-do

Single source of truth for everything that is **not** finished, why it is waiting,
and what "done" means. Update this file whenever an item ships or a gate changes.

Last updated: **2026-11-28**
Production: frontend `https://lead-craft-ai.vercel.app`, API `https://project-76ur0.vercel.app`.
Legend: `[x]` done · `[ ]` open · **GATE** = cannot start until the owner decides.

---

## 1. Phase status at a glance

| Phase | Scope | Status | What remains |
|---|---|---|---|
| P0 | Lifecycle, attribution, ICP, BANT, scoring, timeline | ✅ shipped | — |
| P1 | A/B variants, nurture, inbox, analytics, funnel reports | ✅ shipped | — |
| P2 #1–#2 | Reviews/referrals, advanced attribution | ✅ shipped | — |
| P2 providers | Visitor identification + voice/telephony | 📝 design only | Owner budget + vendor + sign-off |
| P3 #1–#3 | Team roles, white-label, billing ledger | ✅ shipped | — |
| P3 #4 | Agency multi-workspace | 🚧 design only | **GATE**: owner sign-off + backup/window |
| P4 | Webhook core, Meta Lead Ads, WhatsApp inbound | ✅ code shipped | **GATE**: Meta/WhatsApp credentials |
| P5 #1–#3 | Booking, ops/audit/export, revenue/ROI | ✅ shipped | — |
| P6 | Duplicate detection + safe merge | ✅ shipped | — |
| P7 #1–#2 | Custom pages + page analytics/attribution | ✅ shipped | Optional builder polish only |

Production is fully usable on the free tier today. Everything still open is either
**owner-gated** (credentials, budget, sign-off) or **optional polish**.

---

## 2. Engineering backlog (no credentials, zero cost)

These can be done without the owner sharing anything. None of them block launch.

### 2.1 Completed in the pending-phase pass

- [x] **Voice/telephony design gate** — `docs/p2-voice-design.md`: provider
      comparison template, Pakistan PTA/number/recording checklist, proposed
      `phone_numbers` + `call_events` schema, cost caps, test plan, sign-off list.
      No code, no keys, no spend.
- [x] **Production preflight script** — `scripts_local/preflight_check.ps1`:
      read-only checks for health, protected endpoints (`401`), unknown-page events
      (`204`), SPA deep links, optional landing config, and the tracked-file secret
      scan. Verified live: **9/9 passed**. Run before/after every deploy.

### 2.2 Optional hardening (free, recommended before public launch)

- [ ] **Public write throttling** — capture and page-event endpoints currently
      rely on the honeypot and payload validation. Add a DB-backed per-IP limit
      (same pattern as auth throttles, hashed keys only) so a script cannot fill
      the leads table. Acceptance: normal form submits unaffected; burst returns
      `429` + `Retry-After`; tests for both.
- [ ] **Self-service password change** — today only
      `backend/scripts/set_password.py` exists. Add an authenticated endpoint with
      current-password verification and throttle reuse. (Listed as a known gap in
      the rotation runbook.)
- [ ] **Auth event audit rows** — failed logins/lockouts are counted but not
      written to the workspace audit log. Add aggregate-only rows (no plaintext
      email/IP) so owners can see abuse attempts.
- [ ] **CI secret scan** — run `scripts_local/check_secrets.ps1` (or an equivalent
      grep) on every push. Free on GitHub Actions; currently manual only.
- [ ] **Token revocation** — 7-day stateless tokens cannot be revoked per device.
      Needs a token-version column or deny-list. Design first; not launch-blocking.
- [ ] **2FA** — deliberately deferred. Not required for the pilot; revisit before
      paid plans.

### 2.3 Optional product polish (decide, do not assume)

- [ ] **Accessibility/keyboard pass** — focus states, labels on icon buttons,
      contrast, and screen-reader names on the public capture form and dashboard.
      Acceptance: keyboard-only submit works; axe/lighthouse has no critical
      issues; no visual regressions.
- [ ] **Public page social preview** — `index.html` has no `description`/OpenGraph
      tags, and the SPA sets `document.title` at runtime. Crawlers that do not run
      JS will not see per-page metadata. Either accept this (documented limit) or
      add a small prerender/edge function — **cost decision**, so do not start
      without approval.
- [ ] **P7 builder polish** — page duplication, templates, image upload, rich
      text, per-block A/B, scheduled publishing. All explicitly out of scope so
      far; each needs its own scope note.
- [ ] **Docs drift check** — after each phase, confirm `README.md`,
      `docs/api-contracts.md` and the roadmap agree with the live API.

---

## 3. Gated: Meta / WhatsApp activation (credentials)

Code is shipped and tested (`docs/p4-plan.md`); only credentials and a live Meta
app are missing. **Do not paste tokens into chat.** Preferred path: the owner sets
them in the Vercel dashboard (backend project → Settings → Environment Variables),
or in `backend/.env` locally for a dry run.

### 3.1 What the owner provides

- [ ] Meta app created, **Webhooks** product added.
- [ ] `META_APP_ID` (not secret, but keep it out of chat anyway).
- [ ] `META_APP_SECRET` → Vercel backend env.
- [ ] `META_VERIFY_TOKEN` → a long random string, set in **both** Vercel and the
      Meta app webhook settings.
- [ ] `META_PAGE_ACCESS_TOKEN` → Vercel backend env (Lead Ads answer fetching).
- [ ] `WHATSAPP_ACCESS_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` → Vercel backend env.
- [ ] Meta app webhook URLs:
      `https://project-76ur0.vercel.app/api/webhooks/meta` and
      `https://project-76ur0.vercel.app/api/webhooks/whatsapp`.
- [ ] Subscribe the app to the page's `leadgen` field and the WhatsApp
      `messages` field.
- [ ] In the app: **Settings → Integrations**, set the workspace's Meta Page ID
      and WhatsApp phone number ID (routing only; no secrets).

### 3.2 Activation sequence (agent)

- [ ] Confirm the env-var names exist in Vercel (values never printed).
- [ ] Redeploy backend; health must still be `200`.
- [ ] `GET /api/webhooks/meta?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…`
      → challenge echoed; wrong token → `403`; missing config → `503`.
- [ ] Send one signed test delivery → appears in the webhook log, routed to the
      correct workspace, no duplicate on replay.
- [ ] Submit one real Meta Lead Ad test lead → exactly one `meta_lead_ad` lead
      with a server-side consent timestamp.
- [ ] Send one WhatsApp message → one `whatsapp_inbound` lead/conversation/message,
      **no auto-reply**.
- [ ] Verify an unknown page/phone id stays `unrouted` and is never assigned to
      another workspace.
- [ ] Run `scripts_local/preflight_check.ps1`; all checks pass.

### 3.3 Definition of done

- [ ] Integration card shows all chips green (`App secret`, `Verify token`,
      `Page token`, `Meta Lead Ads ready`, `WhatsApp inbound ready`).
- [ ] Replayed delivery creates no second lead/message.
- [ ] Ops log shows the deliveries with correct status.
- [ ] No outbound message is ever sent by the platform.

---

## 4. Gated: Agency multi-workspace (P3 #4)

Design: `docs/p3-agency-design.md`. This is the largest remaining change: the
tenant key moves from `user_id` to `workspace_id` across every table.

**GATE — owner must sign off before any code:**

- [ ] Confirm the target model (accounts vs workspaces, per-workspace roles).
- [ ] Approve a database backup + maintenance/rollout window.
- [ ] Accept the effort estimate (4–6 focused sessions) and acceptance tests
      (isolation, idempotent backfill, tenant-404 behaviour).
- [ ] Confirm cross-workspace agency reporting is **later**, not in the same release.
- [ ] Confirm custom domains are **not** included.

Until signed off, the product stays on `User = workspace`; all shipped P3 modules
(team roles, white-label, billing ledger) keep working unchanged.

---

## 5. Gated: P2 provider modules (paid, opt-in)

| Module | Design | Gate |
|---|---|---|
| B2B visitor identification | `docs/p2-provider-design.md` §1 | Monthly cap + vendor + DPA + privacy update |
| Voice / telephony | `docs/p2-voice-design.md` | Written quotes + PTA verification + monthly cap + recording stays off |

No provider SDK, key, webhook or code exists. Nothing in the core product is
blocked if these are never approved.

---

## 6. Owner-only actions (accounts, secrets, infrastructure)

These need dashboard access; the agent must not handle the values.

- [ ] **Rotate every credential exposed outside a password manager** — follow
      `docs/security-rotation-runbook.md` in order: Supabase DB password →
      `SUPABASE_ANON_KEY` → `SUPABASE_SERVICE_ROLE_KEY` → `SECRET_KEY` →
      `GEMINI_API_KEY`. Rotating `SECRET_KEY` logs everyone out (expected).
- [ ] **Delete old Vercel tokens** — `leadcraft-deploy` and `LeadAI-New` at
      https://vercel.com/account/tokens (confirm nothing still uses them first).
- [ ] **Take a Supabase backup** before the agency migration window (and confirm
      the restore path, not just that a backup exists).
- [ ] **Decide the maintenance window** for P3 #4 (low-traffic hours; read-only
      notice if the backfill needs it).
- [ ] **Confirm team scope** — all Vercel commands use `--scope lead-generators`;
      never touch project `cl8wt`.
- [ ] **Confirm production aliases** stay `lead-craft-ai.vercel.app` (frontend)
      and `project-76ur0.vercel.app` (API), or record new ones in the README.

---

## 7. Final go-live checklist (credentials day)

Run in this order; do not skip the backup or the rotation.

1. [ ] Rotate the five exposed credentials (Section 6) and redeploy backend.
2. [ ] Confirm `/api/health` is `200` and the dashboard login works.
3. [ ] Take/confirm a database backup.
4. [ ] Set the Meta/WhatsApp env vars in Vercel (values only in the dashboard).
5. [ ] Add the two webhook URLs + verify token in the Meta app.
6. [ ] Redeploy backend; confirm webhooks answer the handshake (not `503`).
7. [ ] Create the workspace routing ids in **Settings → Integrations**.
8. [ ] Send signed test deliveries: Meta Lead Ads + WhatsApp inbound.
9. [ ] Verify one lead, one conversation, one inbound message, **zero auto-replies**.
10. [ ] Run `scripts_local/preflight_check.ps1 -Slug <real-slug>` → all pass.
11. [ ] Publish one real custom page (`/p/<slug>`), submit the form, confirm the
        lead appears with `landing_page_slug` and page stats increment.
12. [ ] Watch the webhook log and error rate for 24 hours; then mark live.

---

## 8. Definition of done for the "pending phase"

- [x] All non-credential design gates written and linked from the roadmap.
- [x] A read-only production preflight exists and passes.
- [x] Phase status, owner actions and gated items are listed in one place.
- [ ] Optional hardening in §2.2 completed or explicitly deferred by the owner.
- [ ] Credentials provided → §3 and §7 executed.
- [ ] Agency sign-off (if wanted) → §4 executed in its own release.
