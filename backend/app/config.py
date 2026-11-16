"""Application configuration.

All settings come from environment variables (12-factor). A local default
that is harmless (SQLite) keeps the skeleton runnable with zero credentials;
production uses the Supabase Postgres connection string via DATABASE_URL.
Never commit real secrets — see /docs/.env.example.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "virtual-marketing-platform"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Local dev default: SQLite file. Production: Supabase Postgres URL.
    database_url: str = "sqlite:///./dev.db"

    # Third-party keys (Phase 2+). Empty by default = feature disabled.
    anthropic_api_key: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    meta_verify_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
