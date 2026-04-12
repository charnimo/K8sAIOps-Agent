"""Resource listing endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import deployments, pods, services


router = APIRouter()


@router.get("/pods")
def list_pods(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List pods in a namespace."""
    try:
        if all_namespaces:
            return pods.list_all_pods(label_selector=label_selector)
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


@router.get("/pods/{name}/logs")
def get_pod_logs(
    name: str,
    namespace: str = Query(default="default"),
    container: Optional[str] = Query(default=None),
    previous: bool = Query(default=False),
    tail_lines: int = Query(default=100, ge=1, le=1000),
) -> dict:
    """Return pod logs for a container."""
    try:
        return {
            "name": name,
            "namespace": namespace,
            "container": container,
            "previous": previous,
            "logs": pods.get_pod_logs(
                name=name,
                namespace=namespace,
                container=container,
                previous=previous,
                tail_lines=tail_lines,
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pods/{name}/events")
def get_pod_events(name: str, namespace: str = Query(default="default")) -> list[dict]:
    """Return pod events."""
    try:
        return pods.get_pod_events(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pods/{name}/issues")
def get_pod_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return pod issue classification."""
    try:
        return pods.detect_pod_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments")
def list_deployments(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List deployments in a namespace."""
    try:
        if all_namespaces:
            return deployments.list_all_deployments(label_selector=label_selector)
        return deployments.list_deployments(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments/{name}")
def get_deployment(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a deployment summary."""
    try:
        return deployments.get_deployment(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments/{name}/events")
def get_deployment_events(name: str, namespace: str = Query(default="default")) -> list[dict]:
    """Return deployment events."""
    try:
        return deployments.get_deployment_events(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments/{name}/revisions")
def get_deployment_revisions(name: str, namespace: str = Query(default="default")) -> dict:
    """Return deployment revisions."""
    try:
        return deployments.get_deployment_revisions(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments/{name}/rollout-status")
def get_rollout_status(name: str, namespace: str = Query(default="default")) -> dict:
    """Return deployment rollout status."""
    try:
        return deployments.rollout_status(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments/{name}/rollout-history")
def get_rollout_history(name: str, namespace: str = Query(default="default")) -> dict:
    """Return deployment rollout history."""
    try:
        return deployments.rollout_history(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/services")
def list_services(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List services in a namespace."""
    try:
        if all_namespaces:
            return services.list_all_services(label_selector=label_selector)
        return services.list_services(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/services/{name}")
def get_service(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a service summary."""
    try:
        return services.get_service(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
