# P6 #1 — Duplicate lead detection & safe merge (zero-cost)

Goal: clean up the contact book without guessing. Leads that share a real
contact channel (same phone, same email) are grouped, the owner reviews the
group, and only then can the duplicates be folded into one lead with their
history intact. No fuzzy name matching, no external service, no new table.

Roles: every authenticated role can **read** their own workspace's duplicate
groups. The merge deletes lead rows, so it is **owner/admin only** (manager,
agent and viewer get `403`; unauthenticated gets `401`). Every query is
tenant-scoped — another workspace's lead returns `404`.

## Detection rules (exact only)

- **Phone**: keep digits, strip a leading `00`, collapse a leading `92` to `0`,
  then compare the **last 10 digits**. So `0300 1234567`, `+92 300 1234567`,
  `0092-300-1234567` and `3001234567` all match. Numbers with fewer than
  **7 digits** are ignored entirely (too short to be a real key).
- **Email**: trim + lowercase; must contain `@` and be at least 5 characters.
- **No name matching.** Names are never compared, fuzzy or otherwise.
- Groups are formed by union-find: a phone match and an email match chain
  into one group even when the individual leads only share one key.
- Scan cap: the first **5,000** leads per workspace (oldest first). When the
  cap is hit, the response says `truncated: true` rather than pretending the
  scan was complete. At most **200** groups are returned.

## Endpoints

- `GET /api/leads/duplicates?limit=1..200` — groups, matched-on kinds,
  `scanned`, `truncated`, and the rule notes.
- `GET /api/leads/{id}/duplicates` — candidates for one lead, each with
  `matched_on` and honest `conflicts` (e.g. same email but the phones differ).
- `POST /api/leads/merge` — `{primary_id, duplicate_ids (1..10), dry_run}`.
  `dry_run: true` returns exactly the same summary and changes nothing.

## Merge rules (conservative; primary always wins)

- **Primary fields win.** Status, lifecycle stage, source and any non-empty
  field stay as they are. Empty fields (name, area, attribution, grade,
  metadata keys, …) are filled from the first duplicate that has them and
  listed in `fields_filled`.
- **`intent_notes` are kept from every lead**, each duplicate block prefixed
  with `[Merged from lead #<id>]` so nothing is silently dropped.
- **Deal outcomes are never summed.** If the primary already has an outcome it
  wins; a duplicate's amount is reported as a conflict (not revenue) and the
  row is removed. If only duplicates have outcomes, exactly one moves over and
  the rest are reported, not added.
- **Qualification follows the same "unknown is not zero" rule.** A known
  duplicate value fills an *unknown* primary dimension. A known primary value
  is never overwritten; a differing known value is listed as a conflict.
- **Same-channel conversations are merged** into the primary thread with every
  message preserved; different channels move over as separate threads.
- **Nurture enrollments** in a campaign the primary is already in are reported
  as conflicts and removed, never duplicated.
- **Child history moves before rows are deleted**: notes, stage history,
  activities, score history, appointments, review requests, webhook delivery
  links. Leads that named a duplicate as their referrer are relinked to the
  primary; the primary's own referrer is fixed so it can never self-refer.
- **Consent timestamp** becomes the earliest recorded consent across the group.
- One `duplicate_merged` activity is appended to the primary timeline and one
  `lead.merged` audit row records ids/counts only (no contact data).
- The whole merge runs in one transaction; any failure rolls everything back.

## UI (Leads tab)

A **Duplicate leads** panel above the lead list. "Scan for duplicates" loads
grouped matches; each group shows the leads with a radio to pick the one to
keep and a per-group **Preview merge** that renders moved counts, filled fields
and conflicts before the confirm button. Non-owner/admin roles see the matches
but the merge buttons are disabled with an explanatory note. After a merge the
lead list refreshes.

## Tests

`backend/tests/test_dedupe.py` (8 tests, SQLite, no network): normalization and
grouping, tenant isolation, role gates, dry-run does nothing, history moves and
unknowns fill, deal outcomes never sum (report stays at one won deal), same
channel conversation + nurture de-dupe, referral relink.

## Honest limits

- Exact contact matching only — two leads with the same name but different
  phone/email are **not** flagged, and that is intentional.
- Scans stop at 5,000 leads; larger workspaces see a `truncated` flag.
- A merge cannot be undone from the UI. The ops export/audit trail records what
  happened, but restoring deleted rows is a manual DB operation.
- At most 10 duplicates can be merged into one primary per request.
