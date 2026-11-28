# LeadCraft AI

SaaS for SMBs/agencies/real-estate: AI content automation + compliant lead generation + CRM.

**Current AI setup:** offline mock by default (zero cost, clearly labeled); Google Gemini free-tier adapter built and contract-tested — add a free key from https://aistudio.google.com/api-keys (no credit card), set `LLM_PROVIDER=gemini` + `GEMINI_API_KEY` in `backend/.env`, restart, done. No key required to run the whole product.

**Ground rules (roadmap Section 0, enforced):** consent-based leads only, official WhatsApp Business Cloud API only, no group scraping/auto-joining, no outbound cold messaging. Every lead stores `source` + `consent_timestamp` for audit.

## Stack
- Backend: Python 3.11 + FastAPI + SQLAlchemy
- Frontend: React 18 + Vite + Tailwind CSS
- DB: Supabase Postgres in production; local dev defaults to SQLite
- Later phases: APScheduler/Celery, Claude API, WhatsApp Cloud API, Chatwoot, n8n

## Quick start (local, zero credentials needed)

Backend:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Frontend (second terminal):
```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` — the dashboard shows backend health.

Tests:
```bash
cd backend
pytest
```

## Phase status
| Phase | Scope | Status |
|---|---|---|
| 1 | Skeleton, health API, auth (register/login/me), DB schema (6 tables), Supabase connected, deploy pipeline | ✅ done + deployed |
| 2 | AI content engine + scheduling | ✅ core done: generate (mock/gemini), schedule, due-worker, settings personalization, Content+Settings UI |
| 3 | Compliant lead capture (Meta Lead Ads, landing pages, property module) | 🚧 core done: landing pages `/l/<slug>` + custom block pages `/p/<slug>` with cookie-free page analytics and per-page lead filtering (P7 #1–#2) + consent-first capture + 18 business-type templates with per-industry landing extras + lead notes + search/filter + CSV export + manual platform-CSV import; Meta webhook pending dev account |
| 4 | WhatsApp chatbot + CRM funnel (Chatwoot + n8n) | not started |
| 5 | Integration, pilot | not started |

**Admin dashboard (Phase 3D):** platform-staff accounts (`users.is_admin`) see aggregate stats (businesses, leads by source/status, recent signups) at the **Admin** nav item; individual leads stay user-scoped (privacy). Create: `python scripts/make_admin.py <email> <password>`.

## Live deployment (Vercel, free tier)

- **Frontend:** https://lead-craft-ai.vercel.app (dashboard at `/`, public landing pages at `/l/<slug>` and custom block pages at `/p/<slug>`)
- **API:** https://lead-craft-api.vercel.app (FastAPI on Vercel Functions, Python 3.12)
- **DB:** Supabase Postgres (pooler); env vars live in Vercel project settings — never in the repo
- Deploy: `powershell -ExecutionPolicy Bypass -File scripts_local/vercel_deploy.ps1 -Which backend|frontend` (requires `npx vercel@latest login` as a `lead-generators` team member; no token file)
- Serverless notes: background worker loop is disabled (`APP_DISABLE_SCHEDULER=1`); due scheduled posts flip to `ready_to_publish` lazily on posts read. Cold starts re-run `create_all` (idempotent).

## Security

- Rotation runbook (after any leak): `docs/security-rotation-runbook.md`.
- Scan tracked files for common secret patterns (never prints values):
  `powershell -ExecutionPolicy Bypass -File scripts_local/check_secrets.ps1`.
- `ENVIRONMENT=production` refuses to boot when `SECRET_KEY` is missing or the
  known dev default; tokens are HMAC-signed with a 7-day TTL.
- Login/registration are throttled (DB-backed, SHA-256 keys only): 5 failures
  per email+IP / 15 min, 30 per IP / 15 min, 5 sign-ups per IP / hour → `429`
  with `Retry-After`. Correct passwords are refused while locked, and unknown
  emails cost the same PBKDF2 time as real ones.
- Reset a login password without a dashboard:
  `backend/scripts/set_password.py --email <account>` (prompted, not echoed).
- Only `VITE_API_BASE` belongs in the frontend Vercel project; DB/LLM/signing
  keys live only on the backend project.

## Notes
- Secrets: copy `docs/.env.example` → `backend/.env`; never commit real keys.
- `docs/api-contracts.md` lists current + planned endpoints and the consent rules encoded in them.
- Phase 1 uses `create_all()` for MVP; add Alembic migrations before real production data.
