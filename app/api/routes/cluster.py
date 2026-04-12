"""Cluster, namespace, node, and storage endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import namespaces, nodes, storage
from app.api.mutations import run_direct_action
from app.schemas.mutations import CreatePvcRequest, NodeDrainRequest, PatchPvcRequest


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


@router.post("/nodes/{name}/cordon")
def cordon_node(name: str) -> dict:
    """Cordon a node directly."""
    return run_direct_action("cordon_node", name=name)


@router.post("/nodes/{name}/uncordon")
def uncordon_node(name: str) -> dict:
    """Uncordon a node directly."""
    return run_direct_action("uncordon_node", name=name)


@router.post("/nodes/{name}/drain")
def drain_node(name: str, payload: NodeDrainRequest) -> dict:
    """Drain a node directly."""
    return run_direct_action("drain_node", name=name, params=payload.model_dump())


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


@router.post("/storage/pvcs")
def create_pvc(payload: CreatePvcRequest) -> dict:
    """Create a PVC directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_pvc", name=name, namespace=namespace, params=params)


@router.patch("/storage/pvcs/{name}")
def patch_pvc(name: str, payload: PatchPvcRequest) -> dict:
    """Patch a PVC directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("patch_pvc", name=name, namespace=namespace, params=params)


@router.delete("/storage/pvcs/{name}")
def delete_pvc(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a PVC directly."""
    return run_direct_action("delete_pvc", name=name, namespace=namespace)


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
