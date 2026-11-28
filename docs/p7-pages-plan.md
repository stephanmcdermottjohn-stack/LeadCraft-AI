# P7 — Custom landing pages: block builder (#1) + analytics (#2)

Goal: let a workspace publish more than one landing page without touching the
template-driven page. A page is a list of validated, **text-only** blocks on its
own public URL (`/p/<slug>`); the consent-first capture endpoint is reused, so
there is no second lead-write path and no new external service.

Additive by design: `/l/<slug>` (business template page, A/B variants, booking,
property extras) is untouched.

## Scope shipped

| Piece | Detail |
| --- | --- |
| Table | `landing_pages` (`user_id`, unique `slug`, `title`, `blocks_json`, `is_published`, timestamps) |
| Block types | `hero`, `text`, `features`, `testimonial`, `faq`, `cta` |
| Caps | 12 blocks/page, 6 feature items, 8 FAQ items, 20 pages/workspace |
| String caps | hero heading 120 / subheading 400 / CTA 60; text body 2,000; feature title 80 / body 300; quote 500 / author 100; FAQ question 200 / answer 800 |
| Public URL | `/p/<slug>` — 3–60 lowercase letters/digits/inner hyphens; reserved words blocked |
| Capture | `POST /api/leads/capture` with `page_slug` (optionally `slug` too) |
| Roles | reads: any active member; writes: owner/admin/manager (viewer 403, agent 403) |
| Audit | `page.created`, `page.updated`, `page.deleted` (slug + counts, never personal data) |

## Safety rules

- **No HTML.** Every stored value is a plain string. Unknown block types and
  unknown keys are rejected/dropped server-side; the React renderer escapes all
  text, so markup is displayed literally, never executed.
- **Drafts are private.** `GET /api/public/pages/{slug}` returns `404` unless the
  page is published. Unpublishing hides it again immediately.
- **Same consent contract.** The public form still requires `consent: true` and
  at least one of phone/email, keeps the `company` honeypot, and records
  `consent_timestamp` server-side. No auto-send/outbound messaging.
- **Tenant scoping.** All CRUD queries are `user_id`-scoped (workspace owner),
  so another workspace's page id returns `404`. Slug uniqueness is global to
  keep public URLs unambiguous.
- **Honest limits.** The public response exposes `limits` (`no_booking_widget`,
  `no_html`) so the client does not promise features that are not there.
- **Mismatch guard.** Passing both `slug` and `page_slug` is allowed only when
  both resolve to the same workspace; otherwise `400`.

## API

- `GET /api/pages` → `{pages: [...], limit: 20}`
- `POST /api/pages` `{slug, title, blocks, is_published?}` → `201 {page}`
- `PATCH /api/pages/{id}` (partial) → `{page}`; slug conflicts → `409`
- `DELETE /api/pages/{id}` → `204`
- `GET /api/public/pages/{slug}` → published config + branding + `capture`
  (`page_slug`, optional `business_slug`, consent hint) + `limits`
- `POST /api/leads/capture` — `slug` is now optional when `page_slug` is sent;
  `metadata["landing_page"]` stores the converting custom page slug (no PII).

## Migration & deploy

- `Base.metadata.create_all` creates `landing_pages` on boot.
- Explicit/idempotent option: `python scripts/add_landing_pages.py` (from
  `backend/`, requires a Postgres `DATABASE_URL`).
- Tests: `tests/test_pages.py` (CRUD/slug rules, block validation + caps,
  tenant isolation, viewer/agent gates, draft vs published, capture via
  `page_slug`, mismatch guard, 20-page cap).

## Frontend

- Settings → **Custom landing pages**: list, create/edit blocks, reorder,
  publish/unpublish, delete, view public link.
- `/p/<slug>` public renderer: blocks + a compact consent form (name, phone,
  email, optional message). CTA/hero buttons scroll to the form.
- No booking widget, no A/B variants, no property extras on custom pages —
  those stay on `/l/<slug>` and are documented as limits.

## Deliberately out of scope

- Rich text/HTML, images upload (URLs only), custom domains, per-block A/B,
  scheduled publishing, page duplication/templates. These would add cost or
  risk and are separate decisions.

# P7 #2 — Custom page analytics & per-page leads

Goal: close the measurement gap created by P7 #1. A custom page can now show
how many people visited it, how many started the form and how many leads it
produced — without cookies, PII or an external analytics service.

## What shipped

| Piece | Detail |
| --- | --- |
| Event capture | `POST /api/public/pages/{slug}/events` (`page_view`, `form_start`, `submit`), published pages only, silent `204` |
| Path safety | The server stores `/p/<slug>` itself; a spoofed path cannot pollute `/l/<slug>` numbers |
| Page stats | `GET /api/pages` adds grouped `views`, `leads`, `conversion_pct`, `conversion_known` (30-day window) |
| Page report | `GET /api/pages/{id}/analytics?days=…` reuses the existing analytics summary (daily buckets, honest notes) |
| Lead attribution | `leads.landing_page_slug` column (nullable, indexed); capture sets it and reports expose it |
| Lead filter | `GET /api/leads?page=<slug>` + Leads-list dropdown, source badge and CSV column |
| Frontend | Settings page list shows 30-day views/leads; "Stats" expands visitors/starts/submits plus a 7-day table |

## Honest reporting rules

- Rates are raw facts (e.g. 1 lead / 3 views = `33.3%`) but are labelled **too
  early** until 30 views; no estimated or projected numbers.
- Events are first-party and cookie-free: ad blockers or JS-disabled visitors
  may be missing, and this is stated in the report notes.
- Client-side `submit` events can repeat; server-side lead captures are the
  authoritative number.
- Template-page leads never inflate a custom page: the report filters on
  `landing_page_slug`.

## Migration

Additive, idempotent: `python scripts/add_page_lead_source.py` (from `backend/`)
adds `leads.landing_page_slug` and its index, then backfills any leads that were
captured between P7 #1 and P7 #2 from their existing `metadata.landing_page`
value. Important: `create_all` creates missing tables but **not** missing
columns, so this must run before the backend that reads the column is deployed.

## Caveat: renaming a slug

Renaming changes `/p/<old>` to `/p/<new>`. Historical analytics events and lead
attribution keep the old slug (history is never rewritten), so the page's stats
start from zero under the new slug and old links stop working. The editor warns
about this before saving.

