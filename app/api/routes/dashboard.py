"""Dashboard endpoints."""

from fastapi import APIRouter, HTTPException, Query

from Tools import diagnostics


router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(namespace: str = Query(default="default")) -> dict:
    """Return a lightweight namespace overview for dashboard cards."""
    try:
        return diagnostics.quick_summary(namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

