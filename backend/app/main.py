"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db as db_module
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.config import get_settings
from app.models import Base


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.db_engine = db_module.engine

    # Frontend origin; tighten per environment in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)

    # MVP convenience: create tables on boot. Replace with Alembic before
    # any real production data exists.
    Base.metadata.create_all(bind=db_module.engine)

    return app


app = create_app()
