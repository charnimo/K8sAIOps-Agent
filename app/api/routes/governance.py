"""Governance and scaling endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import hpa, rbac, resource_quotas


router = APIRouter()


@router.get("/service-accounts")
def list_service_accounts(
    namespace: str = Query(default="default"),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List service accounts."""
    try:
        if all_namespaces:
            return rbac.list_all_service_accounts()
        return rbac.list_service_accounts(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/service-accounts/{name}")
def get_service_account(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a service account."""
    try:
        return rbac.get_service_account(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/roles")
def list_roles(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List namespace roles."""
    try:
        return rbac.list_roles(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/roles/{name}")
def get_role(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a namespace role."""
    try:
        return rbac.get_role(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cluster-roles")
def list_cluster_roles(label_selector: Optional[str] = Query(default=None)) -> list[dict]:
    """List cluster roles."""
    try:
        return rbac.list_cluster_roles(label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cluster-roles/{name}")
def get_cluster_role(name: str) -> dict:
    """Fetch a cluster role."""
    try:
        return rbac.get_cluster_role(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/role-bindings")
def list_role_bindings(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List role bindings."""
    try:
        return rbac.list_role_bindings(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/role-bindings/{name}")
def get_role_binding(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a role binding."""
    try:
        return rbac.get_role_binding(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cluster-role-bindings")
def list_cluster_role_bindings(
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List cluster role bindings."""
    try:
        return rbac.list_cluster_role_bindings(label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cluster-role-bindings/{name}")
def get_cluster_role_binding(name: str) -> dict:
    """Fetch a cluster role binding."""
    try:
        return rbac.get_cluster_role_binding(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/hpas")
def list_hpas(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List HPAs."""
    try:
        if all_namespaces:
            return hpa.list_all_hpas(label_selector=label_selector)
        return hpa.list_hpas(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/hpas/{name}")
def get_hpa(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch an HPA."""
    try:
        return hpa.get_hpa(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/hpas/{name}/issues")
def get_hpa_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return HPA issue classification."""
    try:
        return hpa.detect_hpa_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resource-quotas")
def list_resource_quotas(namespace: str = Query(default="default")) -> list[dict]:
    """List resource quotas."""
    try:
        return resource_quotas.list_resource_quotas(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/resource-quotas/{name}")
def get_resource_quota(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a resource quota."""
    try:
        return resource_quotas.get_resource_quota(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/limit-ranges")
def list_limit_ranges(namespace: str = Query(default="default")) -> list[dict]:
    """List limit ranges."""
    try:
        return resource_quotas.list_limit_ranges(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/limit-ranges/{name}")
def get_limit_range(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a limit range."""
    try:
        return resource_quotas.get_limit_range(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/quota-pressure")
def get_quota_pressure(namespace: str = Query(default="default")) -> dict:
    """Return namespace quota pressure analysis."""
    try:
        return resource_quotas.detect_quota_pressure(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
