"""Resource listing endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from kubernetes.client.exceptions import ApiException

from Tools import deployments, pods, services
from app.api.mutations import run_direct_action
from app.schemas.mutations import (
    CreateServiceRequest,
    DeploymentEnvPatchRequest,
    DeploymentResourceLimitsPatchRequest,
    DeploymentRollbackRequest,
    PatchServiceRequest,
    PodExecRequest,
    ScaleRequest,
)


router = APIRouter()


def _raise_pod_lookup_http_exception(exc: ApiException, name: str, namespace: str) -> None:
    """Translate common pod lookup failures into API-friendly responses."""
    if exc.status == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Pod '{name}' not found in namespace '{namespace}'",
        ) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    except ApiException as exc:
        _raise_pod_lookup_http_exception(exc, name=name, namespace=namespace)
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


@router.delete("/pods/{name}")
def delete_pod(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a pod directly."""
    return run_direct_action("delete_pod", name=name, namespace=namespace)


@router.post("/pods/{name}/exec")
def exec_pod(name: str, payload: PodExecRequest, namespace: str = Query(default="default")) -> dict:
    """Execute a command in a pod."""
    return run_direct_action(
        "exec_pod",
        name=name,
        namespace=namespace,
        params=payload.model_dump(),
    )


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


@router.patch("/deployments/{name}/scale")
def scale_deployment(name: str, payload: ScaleRequest, namespace: str = Query(default="default")) -> dict:
    """Scale a deployment directly."""
    return run_direct_action(
        "scale_deployment",
        name=name,
        namespace=namespace,
        params=payload.model_dump(),
    )


@router.post("/deployments/{name}/restart")
def restart_deployment(name: str, namespace: str = Query(default="default")) -> dict:
    """Restart a deployment directly."""
    return run_direct_action("restart_deployment", name=name, namespace=namespace)


@router.post("/deployments/{name}/rollback")
def rollback_deployment(name: str, payload: DeploymentRollbackRequest) -> dict:
    """Rollback a deployment directly."""
    return run_direct_action(
        "rollback_deployment",
        name=name,
        namespace=payload.namespace,
        params={"revision": payload.revision},
    )


@router.patch("/deployments/{name}/resource-limits")
def patch_deployment_resource_limits(name: str, payload: DeploymentResourceLimitsPatchRequest) -> dict:
    """Patch deployment resource limits directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action(
        "patch_resource_limits",
        name=name,
        namespace=namespace,
        params=params,
    )


@router.patch("/deployments/{name}/env")
def patch_deployment_env(name: str, payload: DeploymentEnvPatchRequest) -> dict:
    """Patch deployment environment variables directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action(
        "patch_env_var",
        name=name,
        namespace=namespace,
        params=params,
    )


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


@router.post("/services")
def create_service(payload: CreateServiceRequest) -> dict:
    """Create a service directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_service", name=name, namespace=namespace, params=params)


@router.patch("/services/{name}")
def patch_service(name: str, payload: PatchServiceRequest) -> dict:
    """Patch a service directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("patch_service", name=name, namespace=namespace, params=params)


@router.delete("/services/{name}")
def delete_service(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a service directly."""
    return run_direct_action("delete_service", name=name, namespace=namespace)
