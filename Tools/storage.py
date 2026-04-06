"""
tools/storage.py

Kubernetes storage resource operations (PersistentVolumes, PersistentVolumeClaims, StorageClasses).

Operations:
  READ:  list_pvs, get_pv, list_pvcs, get_pvc, list_storage_classes, get_storage_class, detect_pvc_issues
  WRITE: create_pvc, delete_pvc, patch_pvc
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1
from .utils import fmt_time, retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_pvs(label_selector: Optional[str] = None) -> list[dict]:
    """
    List all PersistentVolumes in the cluster.

    Args:
        label_selector: Optional label filter (e.g., "tier=gold")

    Returns:
        List of PV summaries with name, capacity, access modes, phase, storageclass, claim
    """
    try:
        v1 = get_core_v1()
        pvs = v1.list_persistent_volume(label_selector=label_selector)
        return [_summarize_pv(pv) for pv in pvs.items]
    except ApiException as e:
        logger.error(f"Failed to list PVs: {e}")
        return []


def get_pv(name: str) -> dict:
    """Get a single PersistentVolume by name."""
    try:
        v1 = get_core_v1()
        pv = v1.read_persistent_volume(name)
        return _summarize_pv(pv)
    except ApiException as e:
        logger.error(f"Failed to get PV {name}: {e}")
        return {"error": str(e)}


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_pvcs(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List PersistentVolumeClaims in a namespace.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label filter

    Returns:
        List of PVC summaries
    """
    try:
        v1 = get_core_v1()
        pvcs = v1.list_namespaced_persistent_volume_claim(namespace, label_selector=label_selector)
        return [_summarize_pvc(pvc) for pvc in pvcs.items]
    except ApiException as e:
        logger.error(f"Failed to list PVCs in {namespace}: {e}")
        return []


def get_pvc(name: str, namespace: str = "default") -> dict:
    """Get a single PersistentVolumeClaim."""
    try:
        v1 = get_core_v1()
        pvc = v1.read_namespaced_persistent_volume_claim(name, namespace)
        return _summarize_pvc(pvc)
    except ApiException as e:
        logger.error(f"Failed to get PVC {namespace}/{name}: {e}")
        return {"error": str(e)}


def list_storage_classes() -> list[dict]:
    """List all StorageClasses in the cluster."""
    try:
        from kubernetes.client import StorageV1Api
        sc_api = StorageV1Api()
        scs = sc_api.list_storage_class()
        return [_summarize_storage_class(sc) for sc in scs.items]
    except ApiException as e:
        logger.error(f"Failed to list StorageClasses: {e}")
        return []


def get_storage_class(name: str) -> dict:
    """Get a single StorageClass."""
    try:
        from kubernetes.client import StorageV1Api
        sc_api = StorageV1Api()
        sc = sc_api.read_storage_class(name)
        return _summarize_storage_class(sc)
    except ApiException as e:
        logger.error(f"Failed to get StorageClass {name}: {e}")
        return {"error": str(e)}


def detect_pvc_issues(name: str, namespace: str = "default") -> dict:
    """
    Detect issues with a PVC (pending, lost, etc.).

    Returns:
        {"issues": [str], "severity": "healthy" | "warning" | "critical"}
    """
    try:
        v1 = get_core_v1()
        pvc = v1.read_namespaced_persistent_volume_claim(name, namespace)
    except ApiException as e:
        return {"issues": [f"PVC not found: {e}"], "severity": "critical"}

    issues = []
    phase = pvc.status.phase if pvc.status else None

    if phase == "Pending":
        issues.append("PVC is Pending - may not have a bound PV yet")
    elif phase == "Lost":
        issues.append("PVC is Lost - backing storage unavailable")
    elif phase != "Bound":
        issues.append(f"PVC in unexpected phase: {phase}")

    # Check conditions
    if pvc.status and pvc.status.conditions:
        for cond in pvc.status.conditions:
            if cond.status != "True":
                issues.append(f"Condition {cond.type}: {cond.message}")

    severity = "critical" if phase == "Lost" else "warning" if issues else "healthy"
    return {"issues": issues, "severity": severity}


# ─────────────────────────────────────────────
# WRITE OPERATIONS
# ─────────────────────────────────────────────

def create_pvc(
    name: str,
    namespace: str = "default",
    size: str = "1Gi",
    access_modes: Optional[list[str]] = None,
    storage_class: Optional[str] = None,
    labels: Optional[dict] = None,
) -> dict:
    """
    Create a new PersistentVolumeClaim.

    ⚠️  ACTION — requires user approval.

    Args:
        name:           PVC name
        namespace:      Kubernetes namespace
        size:           Storage size (e.g., "10Gi")
        access_modes:   List of access modes (default: ["ReadWriteOnce"])
        storage_class:  StorageClass name
        labels:         Dict of labels for the PVC

    Returns:
        {"success": bool, "message": str}
    """
    from kubernetes import client

    if not access_modes:
        access_modes = ["ReadWriteOnce"]

    try:
        pvc_body = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels or {}),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=access_modes,
                storage_class_name=storage_class,
                resources=client.V1ResourceRequirements(requests={"storage": size}),
            ),
        )

        v1 = get_core_v1()
        v1.create_namespaced_persistent_volume_claim(namespace, pvc_body)
        logger.info(f"[ACTION] Created PVC {namespace}/{name} ({size})")
        return {"success": True, "message": f"PVC {namespace}/{name} created successfully."}
    except ApiException as e:
        logger.error(f"Failed to create PVC {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def delete_pvc(name: str, namespace: str = "default") -> dict:
    """
    Delete a PersistentVolumeClaim.

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    try:
        v1 = get_core_v1()
        v1.delete_namespaced_persistent_volume_claim(name, namespace)
        logger.info(f"[ACTION] Deleted PVC {namespace}/{name}")
        return {"success": True, "message": f"PVC {namespace}/{name} deleted."}
    except ApiException as e:
        logger.error(f"Failed to delete PVC {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def patch_pvc(name: str, namespace: str = "default", labels: Optional[dict] = None) -> dict:
    """
    Patch a PVC (add/update labels).

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    if not labels:
        return {"success": False, "message": "No labels provided."}

    from kubernetes import client

    try:
        patch_body = {"metadata": {"labels": labels}}
        v1 = get_core_v1()
        v1.patch_namespaced_persistent_volume_claim(name, namespace, patch_body)
        logger.info(f"[ACTION] Patched PVC {namespace}/{name}")
        return {"success": True, "message": f"PVC {namespace}/{name} patched."}
    except ApiException as e:
        logger.error(f"Failed to patch PVC {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_pv(pv) -> dict:
    """Convert PV object to clean dict."""
    capacity = pv.spec.capacity or {}
    storage = capacity.get("storage", "unknown")
    bound_claim = pv.spec.claim_ref

    age = fmt_time(pv.metadata.creation_timestamp) if pv.metadata.creation_timestamp else None

    return {
        "name": pv.metadata.name,
        "capacity": storage,
        "access_modes": pv.spec.access_modes or [],
        "phase": pv.status.phase if pv.status else "Unknown",
        "storage_class": pv.spec.storage_class_name,
        "bound_to": f"{bound_claim.namespace}/{bound_claim.name}" if bound_claim else None,
        "age": age,
        "labels": pv.metadata.labels or {},
    }


def _summarize_pvc(pvc) -> dict:
    """Convert PVC object to clean dict."""
    spec = pvc.spec or {}
    status = pvc.status or {}

    age = fmt_time(pvc.metadata.creation_timestamp) if pvc.metadata.creation_timestamp else None

    return {
        "name": pvc.metadata.name,
        "namespace": pvc.metadata.namespace,
        "size": spec.resources.requests.get("storage", "unknown") if spec.resources else "unknown",
        "access_modes": spec.access_modes or [],
        "storage_class": spec.storage_class_name,
        "phase": status.phase or "Unknown",
        "bound_volume": getattr(status, 'volume_name', None) or getattr(status, 'volumeName', None),
        "age": age,
        "labels": pvc.metadata.labels or {},
    }


def _summarize_storage_class(sc) -> dict:
    """Convert StorageClass object to clean dict."""
    age = fmt_time(sc.metadata.creation_timestamp) if sc.metadata.creation_timestamp else None

    return {
        "name": sc.metadata.name,
        "provisioner": sc.provisioner,
        "reclaim_policy": sc.reclaim_policy or "Delete",
        "volume_binding_mode": sc.volume_binding_mode or "Immediate",
        "default": sc.metadata.annotations.get("storageclass.kubernetes.io/is-default-class")
        == "true"
        if sc.metadata.annotations
        else False,
        "age": age,
        "labels": sc.metadata.labels or {},
    }
