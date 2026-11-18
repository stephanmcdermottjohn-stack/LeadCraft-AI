# AI LeadFlow — P1 execution plan (Conversion & Engagement)

P0 shipped (all live, 74/74 tests): lifecycle stages + stage history, source
attribution, ICP builder + explainable fit, BANT (unknown-first), engagement
score + grade snapshotting, unified activity timeline.

P1 follows the roadmap order, one module per increment, additive only, zero
external cost. Free-first rules unchanged: no scraping, no outbound-first
contact, consent gating everywhere, honest labels, tenant isolation per route.

## Module order

1. **Landing page A/B variants** (gap G, first slice)
   - Variants override headline / subtext / CTA label on the existing auto
     landing page (full block-based page builder stays a later slice).
   - First-party impression events (`landing_events`, no cookies — the
     variant choice persists in the visitor's own localStorage).
   - Report per variant: impressions vs submissions vs *qualified* leads
     (submission is `leads.landing_variant`; "qualified" = left `capture` or
     any BANT dimension known). Missing data is reported as missing.
2. **Nurture workflows v1** (gap H) — consent-gated drip definitions +
   scheduler-driven due steps surfaced as next-actions/activities. No external
   sending provider (email delivery stays deferred with cost-benefit note).
3. **Unified inbox v1** (gap E) — conversations/messages tables already
   exist; API + UI over them, WhatsApp/website-chat first.
4. **Website analytics v1** (gap F) — first-party sessions/events,
   cookie-consent aware.
5. **Funnel + campaign reports** (gap K slice) — actual vs missing data.

## Module 1 scope (this increment)

- New tables: `landing_variants` (user-scoped overrides), `landing_events`
  (impressions; submission/qualified are computed from `leads` honestly).
- Public: extended `GET /api/public/landing/{slug}` (variant assignment),
  `POST /api/public/landing/{slug}/impression` (no-auth count, no PII).
- Auth CRUD: `GET/POST/PATCH/DELETE /api/landing-variants` + report endpoint.
- Capture already accepts `landing_variant` (P0 attribution) — reused.
- Tests target: 74 → ~85. Idempotent migration `add_landing_ab.py`.
