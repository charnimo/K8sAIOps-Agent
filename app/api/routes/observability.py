"""Metrics and observability endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from Tools import metrics
from app.auth.dependencies import require_permission
from app.database.models import User


router = APIRouter()


@router.get("/metrics/pods")
def list_pod_metrics(
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("observability:read")),
) -> list[dict]:
    """List pod metrics in a namespace."""
    try:
        return metrics.list_pod_metrics(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/pods/{name}")
def get_pod_metrics(
    name: str,
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("observability:read")),
) -> dict:
    """Fetch pod metrics."""
    try:
        return metrics.get_pod_metrics(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/nodes")
def list_node_metrics(user: User = Depends(require_permission("observability:read"))) -> list[dict]:
    """List node metrics."""
    try:
        return metrics.list_node_metrics()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/nodes/{name}")
def get_node_metrics(
    name: str,
    user: User = Depends(require_permission("observability:read")),
) -> dict:
    """Fetch node metrics."""
    try:
        return metrics.get_node_metrics(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resource-pressure")
def get_resource_pressure(
    namespace: str = Query(default="default"),
    threshold_pct: Optional[int] = Query(default=None, ge=1, le=100),
    user: User = Depends(require_permission("observability:read")),
) -> dict:
    """Return namespace resource pressure analysis."""
    try:
        return metrics.detect_resource_pressure(namespace=namespace, threshold_pct=threshold_pct)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
