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


@router.get("/events/summary")
def get_warning_summary(
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
) -> list[dict]:
    """Return a compact warning summary for UI and agent context."""
    try:
        return cluster_events.get_recent_warning_summary(namespace=namespace, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/events/resources/{kind}/{name}")
def get_resource_events(
    kind: str,
    name: str,
    namespace: str = Query(default="default"),
) -> list[dict]:
    """Return events for a specific resource."""
    try:
        return cluster_events.get_events_for_resource(name=name, kind=kind, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
