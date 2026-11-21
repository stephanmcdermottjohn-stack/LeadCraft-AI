"""Health-check + system routes (Phase 1 skeleton)."""
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "integrations": {
            "llm_provider": settings.llm_provider,
            "gemini_configured": bool(settings.gemini_api_key),
            "anthropic_configured": bool(settings.anthropic_api_key),
            "whatsapp_configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
            # P4: webhooks are off until the server credentials exist.
            "meta_webhook_configured": bool(settings.meta_app_secret and settings.meta_verify_token),
            "meta_leadgen_configured": bool(
                settings.meta_app_secret and settings.meta_verify_token and settings.meta_page_access_token
            ),
        },
    }
