"""SQLAlchemy engine/session factory.

create_all() runs on startup for MVP convenience; a real migration tool
(e.g. Alembic) is expected before production data exists.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_engine_for_current_settings() -> Engine:
    settings = get_settings()
    # SQLite needs check_same_thread=False under TestClient/uvicorn threads.
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    # pool_pre_ping: serverless hosts (Vercel) and pgbouncer (Supabase pooler)
    # can hand back stale connections; ping before use instead of erroring.
    return create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True, future=True)


engine = create_engine_for_current_settings()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
