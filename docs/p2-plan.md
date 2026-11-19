# AI LeadFlow — P2 execution plan (Advanced Intelligence)

P1 shipped (all live, 97/97 tests): landing A/B variants, nurture workflows,
unified inbox, first-party website analytics, funnel + campaign reports.

P2 keeps the same ground rules: **additive only, zero required external cost,
no scraping, consent-first, honest labels, tenant isolation everywhere**. The
roadmap marks P2 as "design first, then approve" — so paid/provider modules
are deliberately **not built** here; they get a design note + approval gate.

## Module order

1. **Reviews & referrals v1** (this increment) — consent-first, manual
   execution, no fake social proof. **Shipped: `a3341a9`.**
2. **Advanced attribution v1** — campaign registry with *owner-entered* spend
   (ROI only when spend is stated), time-to-qualify/convert, attribution
   coverage. No multi-touch claims: one capture-time attribution set exists.
   **Shipped: `8dadf44`.**
3. *(Design-only, blocked on approval)* **Visitor identification** — see
   `docs/p2-provider-design.md`. No integration until spend is approved.
4. *(Design-only, blocked on approval)* **Voice / telephony** — see
   `docs/p2-provider-design.md`. Pakistan number/regulatory checks first.

## Module 1 scope — reviews & referrals v1
### Reviews
- New table `review_requests`: `user_id, lead_id, channel, status, note,
  requested_at, completed_at`.
- **Consent gate:** the lead must have a recorded `consent_timestamp`.
- **Outcome gate:** reviews can only be requested for leads that actually
  converted (`lifecycle_stage in convert/retain/reactivate` OR CRM
  `status=converted`) — no review asks to prospects.
- Platform **never sends** anything: `requested` means the owner asked through
  their own channel; `completed` / `declined` are logged manually. Rating text
  is not stored or displayed (no fabricated testimonials).
- One active request per lead (409 on duplicate); re-request allowed after a
  completed/declined one.
- Honest summary: requested / completed / declined counts + completion rate
  (`null` when no requests, never 0%).

### Referrals
- `leads.referral_code` (random, unique per business) and
  `leads.referred_by_lead_id` (same-tenant FK, set at capture only — a new lead
  cannot create cycles).
- `POST /api/leads/{id}/referral-code` returns the code + share link
  (`/l/<slug>?ref=<code>`), generating the code on first use.
- Capture accepts `referral_code`; an unknown/cross-tenant code is silently
  ignored (public endpoint never leaks whether a code exists).
- Report: per-referrer referral count / qualified / converted, totals, and a
  rate gate (`null` below 10 referred leads). Only link-based referrals are
  measurable; manual "word of mouth" is explicitly outside the numbers.

### Out of scope (stated, not silently dropped)
- No review scraping, no auto-send, no public testimonial widget.
- No multi-touch attribution, no ad-platform sync, no visitor identification.
- No telephony.

## Effort

Module 1: one session (migration + API + tests + UI cards). Module 2: one
session. Design-only notes: short doc each, no code.
