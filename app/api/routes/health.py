"""Health endpoints."""

from fastapi import APIRouter

from app.core.settings import get_settings


router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """Return application health and basic runtime flags."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.api_title,
        "version": settings.api_version,
        "read_only_mode": settings.read_only_mode,
        "mutations_enabled": settings.mutations_enabled,
    }

