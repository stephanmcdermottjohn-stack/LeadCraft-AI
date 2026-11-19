"""FastAPI application factory."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db as db_module
from app.api.admin import router as admin_router
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.content import router as content_router
from app.api.health import router as health_router
from app.api.icp import router as icp_router
from app.api.inbox import router as inbox_router
from app.api.landing_ab import router as landing_ab_router
from app.api.leads import router as leads_router
from app.api.nurture import router as nurture_router
from app.api.public import router as public_router
from app.api.qualification import router as qualification_router
from app.api.scoring import leads_router as scoring_leads_router, scoring_router as scoring_feedback_router
from app.api.timeline import router as timeline_router
from app.api.settings import router as settings_router
from app.config import get_settings
from app.models import Base


async def _due_posts_loop() -> None:
    """Phase 2 worker loop: flip due scheduled posts to ready_to_publish.
    Honest scope: no auto-publish (Meta app review pending) — status only."""
    from app.db import SessionLocal
    from app.workers.content_worker import run_due_posts_pass

    while True:
        try:
            db = SessionLocal()
            try:
                run_due_posts_pass(db)
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — worker must never kill the app
            pass
        await asyncio.sleep(60)


async def _nurture_loop() -> None:
    """P1 #2 worker loop: surface due nurture touches as next-actions."""
    from app.db import SessionLocal
    from app.workers.nurture_worker import run_due_pass

    while True:
        try:
            db = SessionLocal()
            try:
                run_due_pass(db)
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — worker must never kill the app
            pass
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    nurture_task = None
    if not os.environ.get("APP_DISABLE_SCHEDULER"):
        task = asyncio.create_task(_due_posts_loop())
        nurture_task = asyncio.create_task(_nurture_loop())
    yield
    if task:
        task.cancel()
    if nurture_task:
        nurture_task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.db_engine = db_module.engine

    # Frontend origin; extend via CORS_ORIGINS env (comma-separated) in prod.
    default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    extra_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=default_origins + extra_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(content_router)
    app.include_router(settings_router)
    app.include_router(leads_router)
    app.include_router(public_router)
    app.include_router(icp_router)
    app.include_router(landing_ab_router)
    app.include_router(analytics_router)
    app.include_router(nurture_router)
    app.include_router(inbox_router)
    app.include_router(qualification_router)
    app.include_router(scoring_leads_router)
    app.include_router(scoring_feedback_router)
    app.include_router(timeline_router)
    app.include_router(admin_router)

    # MVP convenience: create tables on boot. Replace with Alembic before
    # any real production data exists.
    Base.metadata.create_all(bind=db_module.engine)

    return app


app = create_app()
