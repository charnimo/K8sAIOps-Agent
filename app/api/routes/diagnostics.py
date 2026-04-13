"""Diagnostics endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import diagnostics
from app.schemas.api import (
    DeploymentDiagnosisRequest,
    ServiceTargetRequest,
    ResourceTargetRequest,
)


router = APIRouter()


@router.post("/pods")
def diagnose_pod(payload: ResourceTargetRequest) -> dict:
    """Run a pod diagnosis bundle."""
    try:
        return diagnostics.diagnose_pod(name=payload.name, namespace=payload.namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pods")
def diagnose_pod_from_query(
    name: str = Query(..., min_length=1),
    namespace: str = Query(default="default", min_length=1),
) -> dict:
    """Run a pod diagnosis bundle from query parameters for browser testing."""
    try:
        return diagnostics.diagnose_pod(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/deployments")
def diagnose_deployment(payload: DeploymentDiagnosisRequest) -> dict:
    """Run a deployment diagnosis bundle."""
    try:
        return diagnostics.diagnose_deployment(
            name=payload.name,
            namespace=payload.namespace,
            include_pod_details=payload.include_pod_details,
            include_resource_pressure=payload.include_resource_pressure,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/deployments")
def diagnose_deployment_from_query(
    name: str = Query(..., min_length=1),
    namespace: str = Query(default="default", min_length=1),
    include_pod_details: bool = Query(default=False),
    include_resource_pressure: bool = Query(default=False),
) -> dict:
    """Run a deployment diagnosis bundle from query parameters for browser testing."""
    try:
        return diagnostics.diagnose_deployment(
            name=name,
            namespace=namespace,
            include_pod_details=include_pod_details,
            include_resource_pressure=include_resource_pressure,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/services")
def diagnose_service(payload: ServiceTargetRequest) -> dict:
    """Run a service diagnosis bundle."""
    try:
        return diagnostics.diagnose_service(name=payload.name, namespace=payload.namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/services")
def diagnose_service_from_query(
    name: str = Query(..., min_length=1),
    namespace: str = Query(default="default", min_length=1),
) -> dict:
    """Run a service diagnosis bundle from query parameters for browser testing."""
    try:
        return diagnostics.diagnose_service(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cluster")
def cluster_health(namespace: Optional[str] = Query(default=None)) -> dict:
    """Return a cluster-wide health snapshot."""
    try:
        return diagnostics.cluster_health_snapshot(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
