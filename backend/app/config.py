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

    app_name: str = "leadcraft-ai"
    app_version: str = "0.2.0"
    environment: str = "development"

    # Local dev default: SQLite file. Production: Supabase Postgres URL.
    database_url: str = "sqlite:///./dev.db"

    # Auth token signing secret (set a long random value in production).
    secret_key: str = "dev-only-insecure-secret-change-me"

    # LLM provider for content generation. "mock" is offline/free and always
    # available; "gemini" uses the Google AI Studio free tier (key from
    # https://aistudio.google.com/api-keys — no credit card). Verified
    # endpoint: POST /v1beta/models/{model}:generateContent (docs checked
    # 2026-11-16). Model name is configurable because model IDs drift.
    llm_provider: str = "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # Future paid provider (kept for Phase 2+ upgrade path; unused while budget=0).
    anthropic_api_key: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    meta_verify_token: str = ""


@lru_cache
def get_settings() -> Settings:
    # Environment variables win over .env defaults (pydantic-settings order),
    # so machine-wide keys like ANTHROPIC_API_KEY do not silently enable a
    # provider the user did not choose — provider selection is explicit.
    return Settings()
