"""Resource listing endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import deployments, pods, services


router = APIRouter()


@router.get("/pods")
def list_pods(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List pods in a namespace."""
    try:
        return pods.list_pods(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pods/{name}")
def get_pod(
    name: str,
    namespace: str = Query(default="default"),
    include_metrics: bool = Query(default=False),
    include_details: bool = Query(default=False),
) -> dict:
    """Fetch a pod status view suitable for the UI."""
    try:
        if include_details:
            return pods.describe_pod(name=name, namespace=namespace)
        if include_metrics:
            return pods.get_pod_status_with_metrics(name=name, namespace=namespace)
        return pods.get_pod_status(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments")
def list_deployments(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List deployments in a namespace."""
    try:
        return deployments.list_deployments(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/services")
def list_services(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List services in a namespace."""
    try:
        return services.list_services(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

