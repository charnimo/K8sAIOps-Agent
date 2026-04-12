"""Event endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import events as cluster_events


router = APIRouter()


@router.get("/events")
def list_events(
    namespace: Optional[str] = Query(default="default"),
    severity: str = Query(default="warning"),
    limit: int = Query(default=20, ge=1, le=500),
) -> list[dict]:
    """Return recent cluster or namespace events."""
    try:
        if severity == "warning":
            return cluster_events.list_warning_events(namespace=namespace, limit=limit)
        if namespace:
            return cluster_events.list_events(namespace=namespace, limit=limit)
        return cluster_events.list_all_events(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

