"""Dashboard endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from Tools import diagnostics
from app.auth.dependencies import require_permission
from app.database.models import User


router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("dashboard:read")),
) -> dict:
    """Return a lightweight namespace overview for dashboard cards."""
    try:
        return diagnostics.quick_summary(namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

