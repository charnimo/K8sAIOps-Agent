"""Audit endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import audit
from app.core.settings import get_settings


router = APIRouter()


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action_type: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
) -> list[dict]:
    """Return recent audit log entries."""
    filter_by = {
        key: value
        for key, value in {
            "action_type": action_type,
            "success": success,
        }.items()
        if value is not None
    }
    return audit.get_action_history(limit=limit, filter_by=filter_by or None)


@router.post("/audit-logs/cleanup")
def cleanup_audit_logs(days: int = Query(default=30, ge=1, le=3650)) -> dict:
    """Delete audit entries older than a threshold."""
    settings = get_settings()
    if settings.read_only_mode:
        raise HTTPException(status_code=409, detail="Audit cleanup is disabled in read-only mode.")

    deleted = audit.clear_old_logs(days=days)
    return {"success": True, "deleted": deleted, "days": days}
