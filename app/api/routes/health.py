"""Health and browser-friendly utility endpoints."""

from fastapi import APIRouter, Response

from app.core.settings import get_settings


router = APIRouter()





@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return an empty favicon response to avoid browser 404 noise."""
    return Response(status_code=204)


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
