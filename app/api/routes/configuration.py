"""Configuration and networking endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import configmaps, ingress, network_policies, secrets


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
    try:
        return secrets.get_secret_values(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


@router.get("/network-policies/{name}")
def get_network_policy(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a network policy."""
    try:
        return network_policies.get_network_policy(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/network-policies/issues")
def get_network_issues(namespace: str = Query(default="default")) -> dict:
    """Return namespace-level network policy issues."""
    try:
        return network_policies.detect_network_issues(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
