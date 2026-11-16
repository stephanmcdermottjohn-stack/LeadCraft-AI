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
| 1 | Skeleton, health API, auth (register/login/me), DB schema (6 tables), Supabase connected, deploy pipeline | ✅ done (local) |
| 2 | AI content engine + scheduling | ✅ core done: generate (mock/gemini), schedule, due-worker, settings personalization, Content+Settings UI |
| 3 | Compliant lead capture (Meta Lead Ads, landing pages, property module) | not started |
| 4 | WhatsApp chatbot + CRM funnel (Chatwoot + n8n) | not started |
| 5 | Integration, pilot | not started |

## Notes
- Secrets: copy `docs/.env.example` → `backend/.env`; never commit real keys.
- `docs/api-contracts.md` lists current + planned endpoints and the consent rules encoded in them.
- Phase 1 uses `create_all()` for MVP; add Alembic migrations before real production data.
