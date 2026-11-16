# Virtual Marketing & Lead Generation Platform

SaaS for SMBs/agencies/real-estate: AI content automation + compliant lead generation + CRM.

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
| 1 | Skeleton, health API, DB schema (6 tables), deploy pipeline | 🚧 in progress |
| 2 | AI content engine + scheduling | not started |
| 3 | Compliant lead capture (Meta Lead Ads, landing pages, property module) | not started |
| 4 | WhatsApp chatbot + CRM funnel (Chatwoot + n8n) | not started |
| 5 | Integration, pilot | not started |

## Notes
- Secrets: copy `docs/.env.example` → `backend/.env`; never commit real keys.
- `docs/api-contracts.md` lists current + planned endpoints and the consent rules encoded in them.
- Phase 1 uses `create_all()` for MVP; add Alembic migrations before real production data.
