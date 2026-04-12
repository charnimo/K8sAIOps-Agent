"""Audit endpoints."""

from typing import Optional

from fastapi import APIRouter, Query

from Tools import audit


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

