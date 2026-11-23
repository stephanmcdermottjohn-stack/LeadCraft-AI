# P5 #3 — Revenue & ROI tracking (zero-cost)

Goal: let the business record what a deal actually earned, and see honest
revenue/ROI numbers next to the leads and campaigns the platform already
tracks — without an invoicing system, a payment gateway, a currency API or any
paid provider.

Roles: **owner/admin/manager** can read and write deal outcomes and see the
revenue report. Agents keep their operational workflow (status, notes,
timeline) but get `403` for money. Viewers are blocked too.

## Data model

New table `deal_outcomes` — **one row per lead** (unique `lead_id`, upsert on
repeat saves):

| Column | Meaning |
|---|---|
| `status` | `open` \| `won` \| `lost` |
| `amount` | number the team typed (0 … 1e12) |
| `currency` | 2–10 letters, normalised to uppercase (`PKR`, `USD`, …) |
| `closed_at` | `YYYY-MM-DD`; forced `null` for `open`, defaults to today for won/lost, never in the future |
| `note` | optional, max 500 chars |
| `created_at`, `updated_at` | timestamps |

Revenue is **manually entered**, never inferred from lead status, pipeline
stage or messages. A lead with no outcome is *unknown*, never zero.

## Endpoints

- `GET /api/leads/{lead_id}/outcome` — current outcome or `null`, plus
  `can_edit`. `404` for another workspace's lead.
- `PUT /api/leads/{lead_id}/outcome` — validate + upsert. Returns
  `{outcome, created, note}`. Invalid status/amount/currency/date → `400`.
- `DELETE /api/leads/{lead_id}/outcome` — removes the row, so revenue becomes
  unknown again. `404` if none exists.
- `GET /api/reports/revenue?days=1..3650` — windowed report (below).

Every write appends an append-only `LeadActivity` (`deal_outcome` /
`deal_outcome_cleared`) so the lead timeline shows who changed what. No
audit-log duplication (P5 #2 scope keeps workspace-level actions separate).

## Report shape (honest labels)

- `outcomes`: `won_deals`, `lost_deals`, `closed_deals`, `open_deals`,
  `win_rate_pct`, `rates_known`, `rate_gate`.
- `coverage`: `leads_total`, `leads_with_outcome`, `coverage_pct`.
- `totals_by_currency[]`: `currency`, `revenue`, `won_deals`, `avg_deal`,
  `lost_deals`, `lost_value`, `open_deals`, `open_value`, `spend`,
  `roi_pct`, `cost_per_won`.
- `campaigns[]`: same idea grouped by lead campaign + currency, with
  `(unattributed)` for won deals that have no campaign.
- `notes[]`: the rules below, stated in the payload itself.

Rules the report enforces:

1. **No currency conversion.** Totals are grouped per currency; PKR and USD
   never add together and there is no exchange-rate API.
2. **Window vs all-time.** Revenue/lost/open count deals whose `closed_at`
   falls in `days`. Campaign spend comes from the existing owner-entered
   ledger which has **no dates**, so ROI mixes an all-time spend total with
   windowed revenue — stated in `notes`.
3. **ROI is null, not 0%.** `roi_pct` and `cost_per_won` are `null` until
   spend exists in the **same currency** *and* at least one won deal is
   recorded. Spend with zero won deals means revenue is unknown, not `-100%`.
4. **Win rate gate.** `win_rate_pct` stays `null` below **10 closed deals** in
   the window (`rates_known: false`). No tiny-sample percentages.
5. **Open deals** carry amount + currency as pipeline value but never count as
   revenue; `lost_value` is reported separately.
6. **Coverage** shows how many leads have any outcome, so a small denominator
   is visible instead of hidden.

## Ops integration

`deal_outcomes` is included in the workspace JSON export (`/api/ops/export`)
and in `/api/ops/usage` counts. No new audit action: lead-level money edits
belong to the lead timeline, per the P5 #2 scope.

## Frontend

- **Leads** → per-lead **Deal** toggle (owner/admin/manager only): status,
  amount, currency, close date (hidden for `open`), note, Save, Remove. Shows
  the saved status on the button and writes to the timeline.
- **Reports** → **Revenue & ROI** card: won/lost/open counts, win rate with
  the unknown gate, coverage, per-currency table (revenue, avg deal, open and
  lost value, spend, ROI, cost per won) and a by-campaign table. Non-manager
  roles see an explicit role notice.

## Out of scope (not built)

- Invoicing, payment collection, gateway reconciliation, refunds.
- Currency conversion / exchange rates.
- Recurring revenue, subscriptions, forecasting or MRR.
- Automated revenue from lead status or messages.
- Per-product line items, taxes, or accounting exports.
