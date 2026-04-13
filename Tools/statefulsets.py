"""
tools/statefulsets.py

StatefulSet operations.

StatefulSets are used for stateful workloads — databases, message queues,
caches (Postgres, Redis, Kafka, etc.). They have ordered pod naming and
stable storage, so their failure modes differ from Deployments.

READ:
  - list_statefulsets(namespace)       → all StatefulSets with status
  - get_statefulset(name, namespace)   → single StatefulSet detail
  - detect_statefulset_issues(name, namespace) → classify problems

ACTIONS (require user approval):
  - scale_statefulset(name, namespace, replicas) → set replica count
  - restart_statefulset(name, namespace)         → rolling restart via annotation patch
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .client import get_apps_v1
from .utils import fmt_duration, fmt_time, retry_on_transient, validate_namespace, validate_name, validate_replicas, sanitize_input
from .audit import audit_statefulset_scale, log_action

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_statefulsets(namespace: str = "default") -> list[dict]:
    """
    List all StatefulSets in a namespace with their status.

    Returns:
        List of StatefulSet summaries with name, replicas, ready count,
        current revision, and container images.
    """
    apps = get_apps_v1()
    try:
        sts_list = apps.list_namespaced_stateful_set(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list StatefulSets in {namespace}: {e}")
        raise
    return [_summarize_statefulset(sts) for sts in sts_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_all_statefulsets() -> list[dict]:
    """List StatefulSets across ALL namespaces."""
    apps = get_apps_v1()
    try:
        sts_list = apps.list_stateful_set_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all StatefulSets: {e}")
        raise
    return [_summarize_statefulset(sts) for sts in sts_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_statefulset(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single StatefulSet."""
    apps = get_apps_v1()
    try:
        sts = apps.read_namespaced_stateful_set(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"StatefulSet {namespace}/{name} not found: {e}")
        raise
    return _summarize_statefulset(sts)


def detect_statefulset_issues(name: str, namespace: str = "default") -> dict:
    """
    Classify what is wrong with a StatefulSet.

    StatefulSet-specific failure modes:
    - NotReady:        fewer ready replicas than desired
    - UpdateStalled:   update revision != current revision (stuck rolling update)
    - Pending:         0 ready replicas
    - PartiallyReady:  some but not all replicas ready

    Returns:
        {
          "issues":   ["NotReady", "UpdateStalled"],
          "severity": "critical" | "warning" | "healthy",
          "details":  { ...summary }
        }
    """
    summary = get_statefulset(name, namespace)
    issues = []

    desired = summary.get("replicas", 0) or 0
    ready   = summary.get("ready_replicas", 0) or 0

    if ready == 0 and desired > 0:
        issues.append("Pending")
    elif ready < desired:
        issues.append("NotReady")
        if ready > 0:
            issues.append("PartiallyReady")

    # A stuck rolling update: update_revision != current_revision
    if (summary.get("update_revision") and summary.get("current_revision")
            and summary["update_revision"] != summary["current_revision"]):
        issues.append("UpdateStalled")

    severity = "healthy"
    if "Pending" in issues or "UpdateStalled" in issues:
        severity = "critical"
    elif issues:
        severity = "warning"

    return {
        "issues":   issues,
        "severity": severity,
        "details":  summary,
    }


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def scale_statefulset(
    name: str,
    namespace: str = "default",
    replicas: int = 1,
) -> dict:
    """
    Scale a StatefulSet to the given replica count.

    ⚠️  ACTION — requires user approval.
    ⚠️  Scaling down a StatefulSet removes pods in reverse ordinal order.
        For stateful workloads this may cause data loss if not handled carefully.

    Args:
        name:      StatefulSet name
        namespace: Namespace
        replicas:  Desired replica count (must be >= 0)

    Returns:
        {"success": bool, "message": str, "previous_replicas": int, "new_replicas": int}
    """
    # Input validation
    name = sanitize_input(name, "statefulset_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    try:
        replicas = validate_replicas(replicas)
    except ValueError as e:
        return {"success": False, "message": f"Invalid input: {str(e)}"}

    apps = get_apps_v1()
    try:
        sts = apps.read_namespaced_stateful_set(name=name, namespace=namespace)
        previous = sts.spec.replicas

        sts.spec.replicas = replicas
        apps.patch_namespaced_stateful_set(name=name, namespace=namespace, body=sts)

        logger.info(f"[ACTION] Scaled StatefulSet {namespace}/{name}: {previous} → {replicas}")
        return {
            "success":           True,
            "message":           f"StatefulSet {namespace}/{name} scaled from {previous} to {replicas} replicas.",
            "previous_replicas": previous,
            "new_replicas":      replicas,
        }
    except ApiException as e:
        logger.error(f"Failed to scale StatefulSet {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def restart_statefulset(name: str, namespace: str = "default") -> dict:
    """
    Trigger a rolling restart of all pods in a StatefulSet.

    Uses the same annotation-patch mechanism as `kubectl rollout restart`.
    Pods are restarted one at a time in reverse ordinal order.

    ⚠️  ACTION — requires user approval.
    """
    # Input validation
    name = sanitize_input(name, "statefulset_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    
    apps = get_apps_v1()
    now = fmt_time(datetime.now(timezone.utc))
    patch_body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": now
                    }
                }
            }
        }
    }
    try:
        apps.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch_body)
        logger.info(f"[ACTION] Rolling restart triggered for StatefulSet {namespace}/{name}")
        log_action(
            "statefulset_restart",
            name,
            namespace,
            success=True,
        )
        return {
            "success": True,
            "message": f"Rolling restart triggered for StatefulSet {namespace}/{name}.",
        }
    except ApiException as e:
        logger.error(f"Failed to restart {namespace}/{name}: {e}")
        log_action(
            "statefulset_restart",
            name,
            namespace,
            success=False,
            error_message=str(e),
        )
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_statefulset(sts) -> dict:
    spec   = sts.spec
    status = sts.status
    creation = sts.metadata.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    containers_info = []
    if spec and spec.template and spec.template.spec:
        for c in spec.template.spec.containers:
            res = {"requests": {}, "limits": {}}
            if c.resources:
                if c.resources.requests:
                    res["requests"] = dict(c.resources.requests)
                if c.resources.limits:
                    res["limits"] = dict(c.resources.limits)
            containers_info.append({
                "name":      c.name,
                "image":     c.image,
                "resources": res,
            })

    # Volume claim templates (how StatefulSets provision per-pod storage)
    pvc_templates = []
    if spec and spec.volume_claim_templates:
        for vct in spec.volume_claim_templates:
            pvc_templates.append({
                "name":          vct.metadata.name,
                "storage_class": vct.spec.storage_class_name,
                "request":       vct.spec.resources.requests.get("storage")
                                 if vct.spec.resources and vct.spec.resources.requests else None,
                "access_modes":  vct.spec.access_modes or [],
            })

    return {
        "name":             sts.metadata.name,
        "namespace":        sts.metadata.namespace,
        "replicas":         spec.replicas if spec else None,
        "ready_replicas":   status.ready_replicas if status else 0,
        "current_replicas": status.current_replicas if status else 0,
        "updated_replicas": status.updated_replicas if status else 0,
        "current_revision": status.current_revision if status else None,
        "update_revision":  status.update_revision if status else None,
        "service_name":     spec.service_name if spec else None,  # headless service
        "update_strategy":  spec.update_strategy.type if spec and spec.update_strategy else None,
        "age":              age,
        "labels":           sts.metadata.labels or {},
        "containers":       containers_info,
        "pvc_templates":    pvc_templates,
    }
