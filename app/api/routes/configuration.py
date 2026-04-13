"""Configuration and networking endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import configmaps, ingress, network_policies, secrets
from app.api.mutations import run_direct_action
from app.core.settings import get_settings
from app.schemas.mutations import (
    CreateConfigMapRequest,
    CreateIngressRequest,
    CreateSecretRequest,
    PatchConfigMapRequest,
    PatchIngressRequest,
    UpdateSecretRequest,
)


router = APIRouter()


@router.get("/configmaps")
def list_configmaps(namespace: str = Query(default="default")) -> list[dict]:
    """List ConfigMaps in a namespace."""
    try:
        return configmaps.list_configmaps(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/configmaps/{name}")
def get_configmap(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a ConfigMap."""
    try:
        return configmaps.get_configmap(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/configmaps")
def create_configmap(payload: CreateConfigMapRequest) -> dict:
    """Create a ConfigMap directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_configmap", name=name, namespace=namespace, params=params)


@router.patch("/configmaps/{name}")
def patch_configmap(name: str, payload: PatchConfigMapRequest) -> dict:
    """Patch a ConfigMap directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("patch_configmap", name=name, namespace=namespace, params=params)


@router.delete("/configmaps/{name}")
def delete_configmap(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a ConfigMap directly."""
    return run_direct_action("delete_configmap", name=name, namespace=namespace)


@router.get("/secrets")
def list_secrets(namespace: str = Query(default="default")) -> list[dict]:
    """List secrets without exposing values."""
    try:
        return secrets.list_secrets(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/secrets/{name}")
def check_secret(name: str, namespace: str = Query(default="default")) -> dict:
    """Return existence and key names for a secret."""
    try:
        return secrets.check_secret(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/secrets/{name}/exists")
def secret_exists(name: str, namespace: str = Query(default="default")) -> dict:
    """Return whether a secret exists."""
    try:
        return {"exists": secrets.secret_exists(name=name, namespace=namespace)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/secrets/{name}/metadata")
def get_secret_metadata(name: str, namespace: str = Query(default="default")) -> dict:
    """Return secret metadata and key names."""
    try:
        return secrets.get_secret_metadata(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/secrets/{name}/values")
def get_secret_values(name: str, namespace: str = Query(default="default")) -> dict:
    """Return plaintext secret values."""
    settings = get_settings()
    if not settings.allow_plaintext_secret_reads:
        raise HTTPException(
            status_code=403,
            detail=(
                "Plaintext secret reads are disabled. "
                "Set AIOPS_ALLOW_PLAINTEXT_SECRET_READS=true only in a trusted environment."
            ),
        )
    try:
        return secrets.get_secret_values(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/secrets")
def create_secret(payload: CreateSecretRequest) -> dict:
    """Create a secret directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_secret", name=name, namespace=namespace, params=params)


@router.patch("/secrets/{name}")
def update_secret(name: str, payload: UpdateSecretRequest) -> dict:
    """Update a secret directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("update_secret", name=name, namespace=namespace, params=params)


@router.delete("/secrets/{name}")
def delete_secret(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a secret directly."""
    return run_direct_action("delete_secret", name=name, namespace=namespace)


@router.get("/ingresses")
def list_ingresses(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List ingresses."""
    try:
        if all_namespaces:
            return ingress.list_all_ingresses(label_selector=label_selector)
        return ingress.list_ingresses(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ingresses/{name}")
def get_ingress(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch an ingress summary."""
    try:
        return ingress.get_ingress(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/ingresses/{name}/issues")
def get_ingress_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return ingress issue classification."""
    try:
        return ingress.detect_ingress_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ingresses")
def create_ingress(payload: CreateIngressRequest) -> dict:
    """Create an ingress directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_ingress", name=name, namespace=namespace, params=params)


@router.patch("/ingresses/{name}")
def patch_ingress(name: str, payload: PatchIngressRequest) -> dict:
    """Patch an ingress directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("patch_ingress", name=name, namespace=namespace, params=params)


@router.delete("/ingresses/{name}")
def delete_ingress(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete an ingress directly."""
    return run_direct_action("delete_ingress", name=name, namespace=namespace)


@router.get("/network-policies")
def list_network_policies(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List network policies."""
    try:
        if all_namespaces:
            return network_policies.list_all_network_policies(label_selector=label_selector)
        return network_policies.list_network_policies(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/network-policies/issues")
def get_network_issues(namespace: str = Query(default="default")) -> dict:
    """Return namespace-level network policy issues."""
    try:
        return network_policies.detect_network_issues(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/network-policies/{name}")
def get_network_policy(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a network policy."""
    try:
        return network_policies.get_network_policy(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
