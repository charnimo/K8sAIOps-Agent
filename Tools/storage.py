"""
Tools/storage.py

Persistent Volume and PVC operations.

READ:
  - list_pvcs(namespace)           → all PVCs with status
  - get_pvc(name, namespace)       → single PVC details
  - check_storage(pod_name, namespace) → detect volume mounting issues for a pod
  - list_pvs()                     → all PersistentVolumes cluster-wide

ACTIONS (require user approval):
  - delete_pvc(name, namespace)    → delete a PVC (dangerous — data loss risk)
"""

import logging
from typing import Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1

logger = logging.getLogger(__name__)


def list_pvcs(namespace: str = "default") -> list[dict]:
    """List all PersistentVolumeClaims in a namespace with their status."""
    core = get_core_v1()
    try:
        pvc_list = core.list_namespaced_persistent_volume_claim(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list PVCs in {namespace}: {e}")
        raise
    return [_summarize_pvc(pvc) for pvc in pvc_list.items]


def get_pvc(name: str, namespace: str = "default") -> dict:
    """Fetch details of a single PVC."""
    core = get_core_v1()
    try:
        pvc = core.read_namespaced_persistent_volume_claim(name=name, namespace=namespace)
        return _summarize_pvc(pvc)
    except ApiException as e:
        logger.error(f"PVC {namespace}/{name} not found: {e}")
        raise


def list_pvs() -> list[dict]:
    """List all PersistentVolumes in the cluster."""
    core = get_core_v1()
    try:
        pv_list = core.list_persistent_volume()
    except ApiException as e:
        logger.error(f"Failed to list PVs: {e}")
        raise
    return [
        {
            "name":             pv.metadata.name,
            "capacity":         pv.spec.capacity.get("storage") if pv.spec.capacity else None,
            "access_modes":     pv.spec.access_modes or [],
            "reclaim_policy":   pv.spec.persistent_volume_reclaim_policy,
            "status":           pv.status.phase if pv.status else "Unknown",
            "claim":            f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"
                                if pv.spec.claim_ref else None,
            "storage_class":    pv.spec.storage_class_name,
        }
        for pv in pv_list.items
    ]


def check_storage(pod_name: str, namespace: str = "default") -> dict:
    """
    Detect volume mounting and PVC issues for a specific pod.

    Checks:
    - Which volumes the pod uses
    - PVC binding status for each volume claim
    - Whether volumes are successfully mounted
    - Pod events related to volume issues

    Returns:
        {
          "volumes":  [...],       # all volumes the pod references
          "pvc_checks": [...],     # status of each PVC-backed volume
          "issues":   [...],       # detected problems
          "recommendations": [...]
        }
    """
    from .pods import get_pod, get_pod_events

    report = {
        "pod_name":        pod_name,
        "namespace":       namespace,
        "volumes":         [],
        "pvc_checks":      [],
        "issues":          [],
        "recommendations": [],
    }

    try:
        pod = get_pod(pod_name, namespace)
    except Exception as e:
        report["issues"].append(f"Could not fetch pod: {e}")
        return report

    # Inspect volumes
    volumes = pod.spec.volumes or []
    for vol in volumes:
        vol_info = {"name": vol.name, "type": "unknown", "source": None}

        if vol.persistent_volume_claim:
            vol_info["type"]   = "PVC"
            vol_info["source"] = vol.persistent_volume_claim.claim_name
            vol_info["read_only"] = vol.persistent_volume_claim.read_only

            # Check PVC status
            try:
                pvc = get_pvc(vol.persistent_volume_claim.claim_name, namespace)
                vol_info["pvc_status"] = pvc["phase"]
                if pvc["phase"] != "Bound":
                    report["issues"].append(
                        f"PVC '{pvc['name']}' is in phase '{pvc['phase']}' (expected 'Bound')"
                    )
                    if pvc["phase"] == "Pending":
                        report["recommendations"].append(
                            f"PVC '{pvc['name']}' is Pending — check StorageClass availability "
                            f"and that the cluster has sufficient storage capacity"
                        )
                    elif pvc["phase"] == "Lost":
                        report["recommendations"].append(
                            f"PVC '{pvc['name']}' is Lost — the underlying PV was deleted. "
                            f"Data may be unrecoverable. Recreate the PVC."
                        )
                report["pvc_checks"].append({**vol_info, "pvc_detail": pvc})
            except Exception as e:
                vol_info["pvc_status"] = "not_found"
                report["issues"].append(f"PVC '{vol.persistent_volume_claim.claim_name}' not found")
                report["recommendations"].append(
                    f"Create PVC '{vol.persistent_volume_claim.claim_name}' in namespace '{namespace}'"
                )
                report["pvc_checks"].append(vol_info)

        elif vol.config_map:
            vol_info["type"]   = "ConfigMap"
            vol_info["source"] = vol.config_map.name
        elif vol.secret:
            vol_info["type"]   = "Secret"
            vol_info["source"] = vol.secret.secret_name
        elif vol.empty_dir is not None:
            vol_info["type"] = "EmptyDir"
        elif vol.host_path:
            vol_info["type"]   = "HostPath"
            vol_info["source"] = vol.host_path.path

        report["volumes"].append(vol_info)

    # Check pod events for volume errors
    try:
        events = get_pod_events(pod_name, namespace)
        volume_event_keywords = [
            "MountVolume", "AttachVolume", "FailedMount",
            "FailedAttachVolume", "VolumeMount", "persistentvolumeclaim"
        ]
        for ev in events:
            if ev.get("type") == "Warning":
                msg = ev.get("message", "").lower()
                reason = ev.get("reason", "")
                if any(kw.lower() in msg or kw.lower() in reason.lower() for kw in volume_event_keywords):
                    report["issues"].append(f"Volume event [{reason}]: {ev.get('message')}")
    except Exception:
        pass

    if not report["issues"]:
        report["assessment"] = "No storage issues detected"
    else:
        report["assessment"] = f"{len(report['issues'])} storage issue(s) detected"

    return report


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def delete_pvc(name: str, namespace: str = "default") -> dict:
    """
    Delete a PersistentVolumeClaim.

    ⚠️  DANGEROUS ACTION — may result in DATA LOSS depending on PV reclaim policy.
    ⚠️  Requires explicit user approval.
    """
    core = get_core_v1()
    try:
        core.delete_namespaced_persistent_volume_claim(name=name, namespace=namespace)
        logger.info(f"[ACTION] Deleted PVC {namespace}/{name}")
        return {
            "success": True,
            "message": f"PVC '{name}' deleted from namespace '{namespace}'. "
                       f"WARNING: Data may be lost depending on the PV reclaim policy.",
        }
    except ApiException as e:
        logger.error(f"Failed to delete PVC {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_pvc(pvc) -> dict:
    return {
        "name":          pvc.metadata.name,
        "namespace":     pvc.metadata.namespace,
        "phase":         pvc.status.phase if pvc.status else "Unknown",
        "capacity":      pvc.status.capacity.get("storage") if pvc.status and pvc.status.capacity else None,
        "access_modes":  pvc.status.access_modes or [],
        "storage_class": pvc.spec.storage_class_name,
        "volume_name":   pvc.spec.volume_name,
        "request":       pvc.spec.resources.requests.get("storage")
                         if pvc.spec.resources and pvc.spec.resources.requests else None,
    }
