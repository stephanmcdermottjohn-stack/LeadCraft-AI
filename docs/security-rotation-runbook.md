# Security pass & credential rotation runbook

Scope: this is a **defensive** pass over the LeadCraft AI repo and its two
Vercel projects. It records what was checked, what was fixed, and the exact
steps to rotate every credential that was ever shared outside a password
manager (including values pasted into chat).

No secret values appear in this document, in git, or in any deployment file.

---

## 1. Findings (audited 2026-11-23)

| Check | Result |
|---|---|
| Git-tracked files for secrets (Google/Groq/OpenAI keys, private keys, Postgres URLs with passwords, JWTs, AWS/GitHub/Slack tokens) | **Clean** — scanner passes on all 139 tracked files |
| Git history (39 commits) for leaked values (`salon-owner-2026`, `LC-admin-…`, `smoke-test-pass-1`, verify token, `AIza`, `gsk_`, `postgresql://`, `eyJhbGciOi`, `service_role`) | **Clean** — only placeholder examples in `docs/.env.example` |
| `.env`, `.env.*`, `.vercel/`, `vcp_*`, `*.log`, `*.db` ignored | **Yes** — verified with `git check-ignore` |
| Frontend Vercel project (`lead-craft-ai`) environment | **Fixed**: it held backend-only `DATABASE_URL`, `SECRET_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `LLM_PROVIDER`, `ENVIRONMENT`, `APP_DISABLE_SCHEDULER`. All removed; only `VITE_API_BASE` remains. The static frontend never needed them. |
| Backend Vercel project (`lead-craft-api`) environment | `SECRET_KEY` present (64 chars, not the dev default), `ENVIRONMENT=production`, `CORS_ORIGINS` = production frontend only, `DATABASE_URL` = Supabase pooler with password |
| Signing key source | **Fixed**: `auth_service` read `os.environ` only, so a key placed only in `backend/.env` was ignored. It now reads through `Settings`, and `create_app()` **fails closed** when `ENVIRONMENT=production` and the key is missing or the known dev default. Test: `tests/test_security.py`. |
| Password storage | PBKDF2-HMAC-SHA256, 390k iterations, 16-byte random salt, constant-time compare |
| Login throttling | **Added**: DB-backed counters (`auth_throttles`, SHA-256 keys only). 5 failures per email+IP / 15 min → 15 min lock; 30 failures per IP / 15 min; register 5 attempts per IP / hour. `429` + `Retry-After`; correct password still refused while locked; unknown emails pay the same PBKDF2 cost. Test: `tests/test_auth_limits.py`. |
| Bearer tokens | HMAC-signed, 7-day TTL, stateless; rotating `SECRET_KEY` invalidates all tokens |
| Webhooks | Fail closed: `503` until the app secret is set; missing/invalid `X-Hub-Signature-256` → `403`; constant-time compare; idempotent event keys |
| CORS | Explicit origins + `CORS_ORIGINS`; no wildcard |
| Local `backend/.env` | Contains `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` — untracked and ignored, but rotate if this machine is shared |

### Known gaps (not fixed in this pass)

- **No 2FA** and only a 7-day stateless token (no per-token revocation list).
- **No self-service password change endpoint** — use `backend/scripts/set_password.py`.
- Failed logins and other auth events are **not** written to the audit log (throttle counters are kept, but the attempts themselves are not event rows).
- No CI job runs the secret scanner yet (run it manually before releases).

---

## 2. Rotation order (do these in order)

Priority is based on exposure: database password first (full data access), then
API keys, then app logins, then tooling tokens.

### 2.1 Supabase database password (highest priority)

The Postgres password was shared in chat.

1. Supabase Dashboard → project `xfmkcxqxkvuenakczvul` → **Project Settings → Database** → **Reset database password** (generate a long random value, store it in a password manager).
2. Update the local connection string: `backend/.env` → `DATABASE_URL` (use the **pooler** host, port `6543`, user `postgres.<ref>`).
3. Update Vercel → project **lead-craft-api** → Settings → Environment Variables → `DATABASE_URL` for **Production and Preview** (dashboard is recommended; never paste the value into chat or shell history).
4. Redeploy the backend:
   ```powershell
   .\scripts_local\vercel_deploy.ps1 -Which backend
   ```
5. Verify: `GET /api/health` → `ok`; log in; open Leads/Reports (DB reads); run a write (note or deal save).
6. Old password is now invalid — if Supabase lists active pooler connections, they drop on reset.

### 2.2 Gemini API key

The key was shared in chat.

1. Google AI Studio → **API keys** → delete/revoke the old key → create a new one.
2. Update `GEMINI_API_KEY` locally (`backend/.env`) and in Vercel **lead-craft-api** (Production + Preview).
3. Optional but recommended: set a project quota/budget alert in Google Cloud so a leaked key cannot run up usage.
4. Redeploy backend. Verify by generating one content post while `LLM_PROVIDER=gemini`.
5. If you do not currently use Gemini, set `LLM_PROVIDER=mock` and remove `GEMINI_API_KEY` from Vercel until needed.

### 2.3 Application login passwords

The owner, admin and smoke-test passwords were shared in chat. Rotate them with
the provided script (same PBKDF2 format as registration; nothing else changes):

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\set_password.py --email owner@gulbergsalon.pk
.\.venv\Scripts\python.exe scripts\set_password.py --email admin@leadcraft.pk
.\.venv\Scripts\python.exe scripts\set_password.py --email smoke-test@local.dev
```

- Omit `--password` so the value is prompted (not stored in shell history).
- Existing bearer tokens stay valid until they expire (7 days) or `SECRET_KEY` is rotated. If you need immediate logout everywhere, see 2.6.
- Verify each login in the UI after the change.
- Consider deleting the `smoke-test@local.dev` account once it is no longer needed (E2E tests can register fresh accounts).

### 2.4 CareerBridge (separate project)

1. **Groq**: Groq console → API keys → revoke the old key → create a new one → update CareerBridge's environment (server-side only).
2. **Supabase**: in the CareerBridge Supabase project, rotate the `anon` and `service_role` keys (Project Settings → API → rotate). Update CareerBridge env.
   - `service_role` must never appear in a browser bundle or a `VITE_*`/`NEXT_PUBLIC_*` variable.
3. Redeploy CareerBridge and smoke-test its main flow.

### 2.5 Vercel CLI session (no token file)

Deploys use the Vercel CLI OAuth device login. The repo no longer stores a token
file, and `.vercel/` CLI state is git-ignored.

1. Log in: `npx vercel@latest login`, then approve the device code in a browser
   signed in as the account that owns the `lead-generators` team.
2. Verify: `npx vercel@latest whoami` prints the owner username and
   `npx vercel@latest teams ls` lists `lead-generators`.
3. Retired API tokens (`leadcraft-deploy`, `LeadAI-New`) are not referenced by the
   repo, CI or Vercel env. Revoke them at Vercel → Account Settings → **Tokens**
   unless an external script still uses them.
4. Never create a **Protection Bypass for Automation** secret for these projects;
   deployment protection stays on.
5. Verify: `.\scripts_local\vercel_deploy.ps1 -Which backend` reaches `READY`.

### 2.6 `SECRET_KEY` (optional, logs everyone out)

Rotating `SECRET_KEY` invalidates **all** bearer tokens; every user must log in
again. Do it during a quiet window.

1. Generate a 64-char random value (password manager).
2. Update `SECRET_KEY` in Vercel **lead-craft-api** (Production + Preview) and locally in `backend/.env`.
3. Redeploy backend. `create_app()` refuses production if the key is empty or the dev default — this is intentional.
4. Verify: old tokens return `401`; fresh login works.

### 2.7 Meta / WhatsApp credentials (when provided)

- `META_APP_ID`, `META_APP_SECRET`, `META_PAGE_ACCESS_TOKEN`, Page ID and WhatsApp phone number ID: enter them in Vercel **lead-craft-api** (Production + Preview) and/or Settings → Integrations for the routing ids. Never in git.
- `META_VERIFY_TOKEN`: already set in Vercel. Rotating it requires updating the Meta App webhook config in the same step.
- Verify: `GET /api/webhooks/meta` handshake echoes the challenge; an unsigned `POST` returns `403`; a signed delivery is accepted once.

---

## 3. Verification checklist (after any rotation)

1. `GET /api/health` → `{"status":"ok"}`.
2. Unauthenticated `GET /api/ops/usage` / `/api/reports/revenue` → `401`.
3. Login works; Leads, Appointments, Reports load real data.
4. One write per area: save a note, save a deal outcome, change a setting.
5. Backend tests: `cd backend; .\.venv\Scripts\python.exe -m pytest -q` (152 passing at the time of this pass).
6. Secret scan: `powershell -ExecutionPolicy Bypass -File scripts_local/check_secrets.ps1` → `PASS`.
7. `git status --short` shows no `.env`, `.vercel/`, logs or DB files.
8. Vercel project env lists contain only what each project needs (frontend: `VITE_API_BASE` only).
9. Throttling (optional prod smoke test): 5 wrong passwords for a non-existent email, then the 6th attempt returns `429` with `Retry-After`. Delete that test row from `auth_throttles` afterwards (`auth_throttles` holds hashed keys only; no user data).

---

## 4. If you suspect a leak

1. Rotate the affected credential immediately (sections above).
2. Redeploy the affected project so the old value is no longer in memory.
3. Review Vercel logs and the workspace audit log (`/api/ops/audit`) for unexpected actions.
4. Rotate `SECRET_KEY` if tokens could have been forged.
5. Run the scanner and `git log -S "<value>" --all` to confirm the value never entered git. If it did, treat history as compromised (rewrite history is not a substitute for rotation).
6. Check Vercel deployment sources for leaked files. `backend/.vercelignore` must
   keep `.env*`, tests, `dev.db`, logs and `scripts/` out of every build:
   ```powershell
   npx vercel@latest api "/v6/deployments?projectId=prj_xXvVvel33LHIYYkB6RtwxRRQKHJW&limit=20" --scope lead-generators
   ```
   then inspect each `dpl_*` with `"/v6/deployments/<id>/files"`. Delete any
   superseded deployment whose tree contains a real `.env` (keep the current
   production deployment). Deleting a deployment does not replace rotation.

---

## 5. Reusable commands

```powershell
# Secret scan of tracked files (no values printed)
powershell -ExecutionPolicy Bypass -File scripts_local/check_secrets.ps1

# Set/reset a login password (prompted, not echoed)
cd backend
.\.venv\Scripts\python.exe scripts\set_password.py --email user@example.com

# Redeploy
cd ..
.\scripts_local\vercel_deploy.ps1 -Which backend
.\scripts_local\vercel_deploy.ps1 -Which frontend
```

Never paste real values into chat, tickets, docs, commit messages, or shell
history. Use the provider dashboard or a password manager, and keep `.env`
local.
