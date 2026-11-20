# P3 — Agency multi-workspace: design + migration path (NOT implemented)

Status: **design only, blocked on explicit approval.** Nothing in this document
is built. The shipped P3 modules (team roles, white-label, billing ledger) all
operate on the current `User = workspace` model and do not depend on this work.

## 1. Why this is a separate, invasive change

Today a `User` row *is* the tenant:

- every data table carries `user_id` (leads, settings, campaigns, spends,
  reviews, conversations, analytics events, billing entries, …);
- every route resolves the tenant through `get_current_user` and filters by
  `user.id`;
- `clients_settings` is 1:1 with `users`;
- team members are re-scoped to the owner's `User` row (P3 #1).

An agency that manages several client businesses needs **one account → many
workspaces**, with per-workspace roles, branding and billing. That cannot be
faked with memberships without either (a) sharing data across clients or
(b) asking the agency to keep several logins. So the tenant key has to move
from `user_id` to `workspace_id`.

## 2. Target model

```
accounts            (id, email, password_hash, is_admin, created_at)
workspaces          (id, name, plan_tier, owner_account_id, created_at)
workspace_members   (id, workspace_id, account_id, role, status, invite_token, …)
workspace_settings  (workspace_id PK, niche, …, brand_name, primary_color, …)
leads / campaigns / … (workspace_id instead of user_id)
billing_entries     (workspace_id, …)
```

- An account can own N workspaces and be a member of N others.
- Roles are per workspace (existing v1 truth table applies per workspace).
- `users.plan_tier` moves to `workspaces.plan_tier`; the billing ledger is
  per workspace. (No payment processing still.)
- White-label fields move to `workspace_settings`.
- The public landing slug becomes globally unique per workspace.

## 3. Migration path (phased, reversible until cutover)

1. **Add new tables** (`accounts` can initially be a view/copy of `users`),
   plus `workspace_id` nullable columns on every data table. No reads change.
2. **Backfill**: one workspace per existing `User` (`workspaces.owner_account_id
   = users.id`, name = `business_name`, plan = `plan_tier`); copy
   `clients_settings` → `workspace_settings`; set `workspace_id` on all rows in
   batches.
3. **Dual-write**: new writes set both `user_id` (legacy) and `workspace_id`.
   The auth dependency starts returning a workspace context
   (`workspace_id`, `role`, `account_id`) while routes may still filter by the
   legacy id during the transition.
4. **Cutover**: switch every query/filter to `workspace_id`; keep `user_id`
   as `created_by` (audit only, nullable). Run the full test suite twice
   (workspace-scoped + isolation tests) before deploying.
5. **Cleanup**: drop redundant columns/constraints in a later migration, after
   a verified backup and a rollback window.

Safety rules: tenant-isolation tests must fail if any endpoint can read another
workspace's rows; the backfill must be idempotent; never re-key history rows
in place without a backup snapshot.

## 4. Code impact (estimate)

- `get_current_user` → `get_workspace_context` (account + workspace + role),
  with a compatibility shim returning the owner account for old routes.
- ~20 API modules: swap `user.id` filters for `workspace_id` (mechanical but
  must be reviewed one by one).
- Services: `scoring`, `reports`, `attribution`, `reviews`, `referrals`,
  `nurture`, `analytics`, `billing`, `team` — all scoped today by `user_id`.
- Frontend: workspace switcher in the sidebar, "create workspace", invite per
  workspace, branding per workspace. Auth state stores the active workspace id.
- Scheduler loops (`nurture`, due posts) iterate over users today; they must
  iterate over workspaces.

**Effort estimate:** 4–6 focused sessions (schema + backfill + dual-write,
route migration, tests, frontend switcher, deploy + verification). No external
cost. Risk: medium-high (touches every table); requires a maintenance window or
careful dual-write rollout.

## 5. What stays design-only

- Custom domains / DNS (hosting cost + certificate handling not approved).
- Cross-workspace analytics for agencies (aggregate reporting across child
  workspaces) — a separate design once the base model exists.
- Ownership transfer / workspace deletion / data export per workspace.

## 6. Approval checklist (owner sign-off)

- [ ] Confirm the target model (accounts vs workspaces, per-workspace roles).
- [ ] Approve a maintenance/rollout window and a database backup before the
      backfill.
- [ ] Approve the effort (4–6 sessions) and the acceptance tests
      (isolation, backfill idempotency, tenant-404 behaviour).
- [ ] Confirm whether agency-level cross-workspace reporting is required in
      the same release (recommended: later).
- [ ] Confirm no custom-domain work is included.

Until this checklist is signed off, the product continues on the current
`User = workspace` model with all shipped P3 modules fully functional.
