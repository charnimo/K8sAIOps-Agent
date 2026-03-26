"""
Tools/rollout.py

Deployment rollout operations.

READ:
  - get_rollout_status(name, namespace)    → current rollout progress + health
  - get_rollout_history(name, namespace)   → revision history with change causes

ACTIONS (require user approval):
  - rollback_deployment(name, namespace, revision) → undo to previous (or specific) revision
"""

import logging
from typing import Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .client import get_apps_v1
from .utils import fmt_time

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def get_rollout_status(name: str, namespace: str = "default") -> dict:
    """
    Return the current rollout progress for a deployment.

    Surfaces whether a rollout is in progress, stalled, or complete, and
    exposes the exact condition messages that explain why.

    Returns:
        {
          "name": str,
          "namespace": str,
          "desired": int,
          "updated": int,      # replicas running the new template
          "ready": int,
          "available": int,
          "rollout_complete": bool,
          "rollout_in_progress": bool,
          "conditions": [...],  # Progressing / Available conditions with messages
          "summary": str,       # human-readable one-liner
        }
    """
    apps = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Deployment {namespace}/{name} not found: {e}")
        raise

    spec   = dep.spec
    status = dep.status

    desired   = spec.replicas or 0
    updated   = status.updated_replicas or 0
    ready     = status.ready_replicas or 0
    available = status.available_replicas or 0

    conditions = []
    if status.conditions:
        for c in status.conditions:
            conditions.append({
                "type":    c.type,
                "status":  c.status,
                "reason":  c.reason,
                "message": c.message,
                "last_update": fmt_time(c.last_update_time),
            })

    rollout_complete   = (updated == desired and ready == desired and available == desired)
    rollout_in_progress = not rollout_complete and updated > 0

    # Detect stalled rollout: Progressing condition with DeadlineExceeded
    stalled = any(
        c["type"] == "Progressing" and c.get("reason") == "ProgressDeadlineExceeded"
        for c in conditions
    )

    if stalled:
        summary = f"Rollout STALLED — deadline exceeded. {ready}/{desired} pods ready."
    elif rollout_complete:
        summary = f"Rollout complete. {ready}/{desired} pods ready and available."
    elif rollout_in_progress:
        summary = f"Rollout in progress: {updated} updated, {ready}/{desired} ready."
    else:
        summary = f"Deployment paused or not yet started. {ready}/{desired} pods ready."

    return {
        "name":               name,
        "namespace":          namespace,
        "desired":            desired,
        "updated":            updated,
        "ready":              ready,
        "available":          available,
        "rollout_complete":   rollout_complete,
        "rollout_in_progress": rollout_in_progress,
        "stalled":            stalled,
        "conditions":         conditions,
        "summary":            summary,
    }


def get_rollout_history(name: str, namespace: str = "default") -> list[dict]:
    """
    Return the revision history of a deployment (via its ReplicaSets).

    Each entry contains the revision number, creation time, image(s), and
    the change-cause annotation if set via kubectl rollout.

    Returns:
        [
          {
            "revision": 3,
            "created_at": "2024-01-15T10:00:00Z",
            "images": ["nginx:1.25"],
            "change_cause": "kubectl set image ...",
            "replicas": 0,   # 0 = old/inactive RS
          },
          ...
        ]
    Sorted newest revision first.
    """
    apps = get_apps_v1()

    # Fetch the deployment to get its selector
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Deployment {namespace}/{name} not found: {e}")
        raise

    selector = dep.spec.selector.match_labels or {}
    label_selector = ",".join(f"{k}={v}" for k, v in selector.items())

    # ReplicaSets owned by this deployment carry the revision annotations
    try:
        rs_list = apps.list_namespaced_replica_set(
            namespace=namespace,
            label_selector=label_selector,
        )
    except ApiException as e:
        logger.error(f"Failed to list ReplicaSets for {namespace}/{name}: {e}")
        raise

    history = []
    for rs in rs_list.items:
        annotations = rs.metadata.annotations or {}
        revision_str = annotations.get("deployment.kubernetes.io/revision")
        if not revision_str:
            continue

        images = []
        if rs.spec and rs.spec.template and rs.spec.template.spec:
            images = [c.image for c in rs.spec.template.spec.containers]

        history.append({
            "revision":     int(revision_str),
            "created_at":   fmt_time(rs.metadata.creation_timestamp),
            "images":       images,
            "change_cause": annotations.get("kubernetes.io/change-cause", ""),
            "replicas":     rs.status.replicas if rs.status else 0,
        })

    history.sort(key=lambda x: x["revision"], reverse=True)
    return history


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def rollback_deployment(
    name: str,
    namespace: str = "default",
    revision: Optional[int] = None,
) -> dict:
    """
    Roll back a deployment to the previous revision or a specific one.

    Implemented by finding the target ReplicaSet and patching the deployment's
    pod template to match it — the same mechanism as `kubectl rollout undo`.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Deployment name
        namespace: Namespace
        revision:  Target revision number. If None, rolls back to the
                   immediately previous revision (current - 1).

    Returns:
        {"success": bool, "message": str, "rolled_back_to_revision": int}
    """
    apps = get_apps_v1()

    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        return {"success": False, "message": f"Deployment not found: {e}"}

    current_revision = int(
        (dep.metadata.annotations or {}).get("deployment.kubernetes.io/revision", "0")
    )

    history = get_rollout_history(name, namespace)
    if not history:
        return {"success": False, "message": "No rollout history found — cannot roll back."}

    # Determine target revision
    if revision is None:
        target_revision = current_revision - 1
    else:
        target_revision = revision

    target_rs_entry = next((h for h in history if h["revision"] == target_revision), None)
    if not target_rs_entry:
        available = [h["revision"] for h in history]
        return {
            "success": False,
            "message": f"Revision {target_revision} not found. Available: {available}",
        }

    # Find the actual ReplicaSet object
    selector = dep.spec.selector.match_labels or {}
    label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
    rs_list = apps.list_namespaced_replica_set(namespace=namespace, label_selector=label_selector)

    target_rs = None
    for rs in rs_list.items:
        annotations = rs.metadata.annotations or {}
        if annotations.get("deployment.kubernetes.io/revision") == str(target_revision):
            target_rs = rs
            break

    if not target_rs:
        return {"success": False, "message": f"Could not locate ReplicaSet for revision {target_revision}."}

    # Patch the deployment's pod template to match the target RS
    patch_body = {
        "spec": {
            "template": target_rs.spec.template.to_dict()
        }
    }

    try:
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch_body)
        logger.info(f"[ACTION] Rolled back {namespace}/{name} to revision {target_revision}")
        return {
            "success":                 True,
            "message":                 f"Deployment {namespace}/{name} rolled back to revision {target_revision}.",
            "rolled_back_to_revision": target_revision,
            "images":                  target_rs_entry["images"],
        }
    except ApiException as e:
        logger.error(f"Failed to roll back {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}
