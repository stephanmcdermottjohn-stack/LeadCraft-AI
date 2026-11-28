# P2 voice / telephony — design gate (NOT implemented)

Status: **design only. Zero code, zero credentials, zero spend.** Nothing in this
document is wired into the product. It exists so the owner can approve or reject
telephony with real numbers instead of assumptions, and so the eventual build
starts from a reviewed plan rather than an experiment.

Companion docs: `docs/p2-provider-design.md` (visitor identification + shared
approval rules), `docs/leadflow-roadmap.md` §7 (cost assessment).

Rule honored: **paid providers are never required for core app function.** Lead
capture, CRM, bookings, inbox, reports and custom pages all work with telephony
switched off forever.

---

## 1. What v1 would do (and would not)

### In scope for a first release
1. **Inbound call log** — a rented business number receives a call; the provider
   webhook stores direction, timestamps, duration and the matched lead.
2. **Click-to-call** — the owner presses "Call" on an existing **consented**
   lead; the provider bridges owner ↔ customer. No dialer, no queue, no campaign.
3. **Lead timeline entry** — `call: inbound 2m 14s` appears next to notes,
   messages, bookings and deal outcomes.
4. **Manual notes** — the owner writes the outcome; the platform never invents a
   summary from audio.

### Explicitly out of scope (v1 and probably forever)
- Auto-dialers, power dialers, robocalls, bulk call campaigns.
- Outbound-first contact to a number that is not an existing consented lead.
- AI voice agents, TTS greetings, STT transcription, sentiment/"intent" scores.
- Recording by default. Recording, if ever enabled, is per-workspace opt-in with
  a spoken consent prompt and a stored consent timestamp.
- Caller-ID spoofing, number rotation, "local presence" tricks.
- Buying, scraping or importing phone lists.

---

## 2. Provider comparison template (quotes required — no invented prices)

Do **not** fill this table from marketing pages. Every row needs a written quote
and a signed DPA before it can be considered. `?` means "unknown until quoted".

| Criterion | Twilio | Telnyx | Vonage | CallHippo | Local PK provider / LDI |
|---|---|---|---|---|---|
| Pakistani number available (landline/mobile) | ? | ? | ? | ? | ? |
| Inbound per-minute rate | ? | ? | ? | ? | ? |
| Outbound per-minute rate to PK mobile | ? | ? | ? | ? | ? |
| Number rental / month | ? | ? | ? | ? | ? |
| Caller ID (verified business number) | ? | ? | ? | ? | ? |
| Webhook signing (HMAC or equivalent) | ? | ? | ? | ? | ? |
| Idempotent event ids + replay window | ? | ? | ? | ? | ? |
| Recording storage + region | ? | ? | ? | ? | ? |
| Data processing agreement / residency | ? | ? | ? | ? | ? |
| Free sandbox or trial number | ? | ? | ? | ? | ? |
| PTA / regulatory posture for PK termination | ? | ? | ? | ? | ? |
| Support responsiveness (PK hours) | ? | ? | ? | ? | ? |
| **Verdict** | | | | | |

### Evaluation procedure (before any integration)
1. Request written quotes for: one PK number, 100 inbound minutes, 100 outbound
   minutes, 1 GB recording storage (if offered), and webhook/API access.
2. Ask each vendor for their PTA/licensing position for Pakistani numbers **in
   writing**, plus where call metadata and audio are stored.
3. Buy **one** sandbox/pilot number for the strongest candidate only.
4. Measure: answer latency, call quality on a PK mobile, webhook delivery delay,
   duplicate/replay behaviour, and whether signatures can actually be verified.
5. Record findings in this table and bring the total to the owner.

---

## 3. Pakistan regulatory & consent checklist (verify, never assume)

- [ ] **PTA / licensing** — confirm whether the vendor is licensed/registered for
      VoIP termination and number provisioning in Pakistan. "Works in a demo"
      is not proof.
- [ ] **Business documentation** — NTN/incorporation/address proof required for a
      local number; note who signs and how long activation takes.
- [ ] **Call recording consent** — determine whether Pakistan requires one-party
      or two-party consent for business calls, and whether an announcement is
      mandatory. Store the consent timestamp with the call row.
- [ ] **Storage location** — where is audio stored, for how long, and who can
      access it? Prefer no recording at all for v1.
- [ ] **Caller ID rules** — confirm the business's own verified number is used;
      no spoofing or dynamic caller ID.
- [ ] **Unsolicited contact rules** — outbound is limited to existing consented
      leads, with quiet hours and an opt-out that is honored permanently.
- [ ] **Retention** — metadata retention default 24 months (configurable), audio
      default **off**; deletion must be possible per lead and per workspace.
- [ ] **Privacy policy** — publish a call-handling section before the first live
      call, including how to request deletion.

If any box cannot be verified, telephony stays off. There is no "we'll fix it
after launch" path for regulatory items.

---

## 4. Data model (proposed; not created)

All tables are workspace-scoped with the current `user_id` tenant key, so the
future agency `workspace_id` migration (P3 #4) can re-key them like every other
table.

### `phone_numbers`
| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | tenant; indexed |
| `e164` | unique per tenant, normalized `+92…` |
| `provider` | `twilio` / `telnyx` / … |
| `provider_number_id` | vendor-side id, **not** a secret |
| `label` | "Main line", "Sales" |
| `status` | `active` / `disabled` |
| `created_at` | |

### `call_events`
| Column | Notes |
|---|---|
| `id` | PK |
| `user_id` | tenant; composite index `(user_id, started_at)` |
| `lead_id` | nullable FK; only when phone match is unambiguous |
| `provider` | vendor key |
| `provider_call_id` | unique per tenant (idempotency key) |
| `direction` | `inbound` / `outbound` |
| `from_number` / `to_number` | E.164, capped length |
| `status` | `ringing` / `answered` / `completed` / `missed` / `failed` |
| `started_at` / `answered_at` / `ended_at` | UTC; server time from webhook |
| `duration_s` | nullable until completed |
| `recording_url` | nullable; **only** when recording consent is stored |
| `recording_consent_at` | nullable; must be set if `recording_url` is set |
| `created_at` | |

Rules encoded in the model:
- Unknown inbound numbers create **no** lead — they remain an unattributed call
  row for the owner to review manually.
- Phone matching uses the same normalized comparison as P6 dedupe (digits,
  last-10, `+92`/`00` collapsed) and only links when exactly one lead matches.
- A `provider_call_id` replay updates nothing; it returns `204`.
- Deleting a lead nulls `lead_id` (history stays) rather than deleting call rows.

---

## 5. API sketch (design only — do not add to `api-contracts.md` until built)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/calls/click-to-call` | Owner-initiated bridge to one consented lead; refuses non-consented, opted-out, quiet-hours, over-cap |
| `POST` | `/api/webhooks/telephony/{provider}` | Signed provider callbacks; verify signature, store-first, idempotent |
| `GET` | `/api/calls?lead_id=&direction=&days=` | Tenant-scoped list |
| `GET` | `/api/leads/{id}/calls` | Call history for one lead |
| `PATCH` | `/api/calls/{id}` | Owner note/outcome only (never timestamps or duration) |

Every response is tenant-scoped; a cross-tenant id returns `404`. Webhooks never
trust the payload's tenant; they resolve it from the rented number. No endpoint
returns provider credentials, recording URLs to non-owners, or full numbers to
non-members.

---

## 6. Timeline & UI integration

- Timeline activity kind `call` with a short detail (`inbound 2m 14s`, `missed`,
  `outbound 0m 41s`) and a link to the call row.
- Lead detail shows calls next to messages and bookings; no separate inbox.
- Dashboard shows **counts only** (calls today / missed today), no "AI call
  score" or other invented metric.
- Settings gets a Telephony card with: enabled toggle (default off), number
  status, monthly cap, recording toggle (default off), and a one-line cost note.
- Every call row shows the provider name and whether the number is verified.

---

## 7. Cost model & hard gates

Monthly cost per workspace (all figures from the signed quote, never estimated):

```
cost = number_rental
     + inbound_minutes  × inbound_rate
     + outbound_minutes × outbound_rate
     + recording_gb     × storage_rate      (only if recording enabled)
     + stt_minutes      × stt_rate           (only if transcription ever approved)
```

Gates that must exist **before** the first live call:
- [ ] Written monthly hard cap per workspace, stored in settings.
- [ ] Pre-call check: if projected spend ≥ cap, the call is refused with a clear
      message (never silently downgraded).
- [ ] `TELEPHONY_ENABLED=0` kill switch that disables calls and webhooks without
      a deploy.
- [ ] Provider-side spend alert set to the same cap.
- [ ] Cost shown in the ops/usage view alongside existing row counts.

No integration starts until the cap is written into this document and approved.

---

## 8. Rollout plan (only after approval)

1. **Design sign-off** — this document reviewed; checklist in §9 signed.
2. **Sandbox** — one test number, fake adapter tests, no customer traffic.
3. **Pilot** — one workspace, one number, inbound logging + click-to-call only.
4. **Review** — 2 weeks of real calls: quality, webhook reliability, actual cost
   vs cap. Recording still off.
5. **Widen** — per-workspace opt-in only; no default-on.
6. **Recording / transcription** — a separate decision, separate document.

If the pilot fails any quality or cost gate, telephony is switched off and the
product continues unchanged.

---

## 9. Test plan (when code exists)

- Fake provider adapter; the whole suite stays offline.
- Signature verification: valid, missing, wrong, replayed.
- Idempotency: same `provider_call_id` twice → one row, second is `204`.
- Consent: non-consented and opted-out leads refuse click-to-call.
- Quiet hours and monthly cap refusal.
- Tenant isolation: cross-tenant call id → `404`; webhook resolves tenant from
  the number, not the body.
- Recording: URL rejected unless `recording_consent_at` is set.
- Kill switch: disabled module returns a clear `503`, no partial writes.
- Timeline merge includes calls without duplicating notes.

---

## 10. Approval checklist (owner sign-off)

Extends `docs/p2-provider-design.md` §3. Every box is required.

- [ ] Approve or reject telephony as a module (default: reject until quotes).
- [ ] Choose the vendor from completed quotes in §2.
- [ ] Approve a monthly hard cap per workspace (number in writing).
- [ ] Confirm the Pakistan regulatory checklist in §3 is fully verified.
- [ ] Confirm recording stays **off** for v1.
- [ ] Confirm no AI voice agent / transcription in v1.
- [ ] Approve the pilot scope (one workspace, one number, 2 weeks).
- [ ] Approve the retention policy (metadata 24 months, audio off).
- [ ] Confirm the kill switch and cap-refusal behaviour.
- [ ] Confirm privacy-policy update is ready before the first live call.

Until every box is checked, **no telephony code, SDK, key or webhook is added.**
The product's core loop remains fully functional without it.
