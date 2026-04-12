"""Cluster, namespace, node, and storage endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import namespaces, nodes, storage


router = APIRouter()


@router.get("/nodes")
def list_nodes() -> list[dict]:
    """List cluster nodes."""
    try:
        return nodes.list_nodes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}")
def get_node(name: str) -> dict:
    """Fetch a node summary."""
    try:
        return nodes.get_node(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/issues")
def get_node_issues(name: str) -> dict:
    """Return node issue classification."""
    try:
        return nodes.detect_node_issues(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/events")
def get_node_events(name: str) -> list[dict]:
    """Return node events."""
    try:
        return nodes.get_node_events(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces")
def list_namespaces() -> list[dict]:
    """List namespaces."""
    try:
        return namespaces.list_namespaces()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}")
def get_namespace(name: str) -> dict:
    """Fetch a namespace summary."""
    try:
        return namespaces.get_namespace(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/resources")
def get_namespace_resource_count(name: str) -> dict:
    """Return resource counts for a namespace."""
    try:
        return namespaces.get_namespace_resource_count(namespace=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/events")
def get_namespace_events(
    name: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """Return namespace events."""
    try:
        return namespaces.get_namespace_events(name=name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvs")
def list_pvs(label_selector: Optional[str] = Query(default=None)) -> list[dict]:
    """List persistent volumes."""
    try:
        return storage.list_pvs(label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvs/{name}")
def get_pv(name: str) -> dict:
    """Fetch a persistent volume summary."""
    try:
        return storage.get_pv(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs")
def list_pvcs(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List persistent volume claims."""
    try:
        return storage.list_pvcs(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}")
def get_pvc(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a persistent volume claim summary."""
    try:
        return storage.get_pvc(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}/issues")
def get_pvc_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return PVC issue classification."""
    try:
        return storage.detect_pvc_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/classes")
def list_storage_classes() -> list[dict]:
    """List storage classes."""
    try:
        return storage.list_storage_classes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/classes/{name}")
def get_storage_class(name: str) -> dict:
    """Fetch a storage class summary."""
    try:
        return storage.get_storage_class(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
