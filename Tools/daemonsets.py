"""
tools/daemonsets.py

DaemonSet operations.

DaemonSets ensure a Pod runs on every Node (or matching nodes).
Used for node-level services: logging agents, monitoring, networking, security.

READ:
  - list_daemonsets(namespace)           → all DaemonSets with status
  - get_daemonset(name, namespace)       → single DaemonSet detail
  - detect_daemonset_issues(name, namespace) → classify problems

ACTIONS (require user approval):
  - restart_daemonset(name, namespace)   → rolling restart via annotation patch
  - update_daemonset_image(name, namespace, container, image) → update container image
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes.client import AppsV1Api
from kubernetes.client.exceptions import ApiException

from .client import get_apps_v1
from .utils import fmt_duration, fmt_time, retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_daemonsets(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List all DaemonSets in a namespace with their status.

    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector

    Returns:
        List of DaemonSet summaries with name, desired, current, ready, updated counts.
    """
    apps: AppsV1Api = get_apps_v1()
    try:
        ds_list = apps.list_namespaced_daemon_set(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list DaemonSets in {namespace}: {e}")
        raise
    return [_summarize_daemonset(ds) for ds in ds_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_all_daemonsets(label_selector: Optional[str] = None) -> list[dict]:
    """List DaemonSets across ALL namespaces.
    
    Args:
        label_selector: Optional Kubernetes label selector
    """
    apps: AppsV1Api = get_apps_v1()
    try:
        ds_list = apps.list_daemon_set_for_all_namespaces(label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list all DaemonSets: {e}")
        raise
    return [_summarize_daemonset(ds) for ds in ds_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_daemonset(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single DaemonSet."""
    apps: AppsV1Api = get_apps_v1()
    try:
        ds = apps.read_namespaced_daemon_set(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"DaemonSet {namespace}/{name} not found: {e}")
        raise
    return _summarize_daemonset(ds)


def detect_daemonset_issues(name: str, namespace: str = "default") -> dict:
    """
    Classify what is wrong with a DaemonSet.

    DaemonSet-specific failure modes:
    - NotReady:        fewer ready pods than desired (some nodes not running pod)
    - Misscheduled:    pods running on nodes they shouldn't be
    - PartiallyReady:  some but not all desired pods are ready

    Returns:
        {
          "issues":   ["NotReady", ...],
          "severity": "critical" | "warning" | "healthy",
          "details":  { ...summary }
        }
    """
    summary = get_daemonset(name, namespace)
    issues = []

    desired = summary.get("desired_number_scheduled", 0) or 0
    ready   = summary.get("number_ready", 0) or 0
    updated = summary.get("updated_number_scheduled", 0) or 0
    misscheduled = summary.get("number_misscheduled", 0) or 0

    if ready == 0 and desired > 0:
        issues.append("NotReady")
    elif ready < desired:
        issues.append("NotReady")
        if ready > 0:
            issues.append("PartiallyReady")

    if misscheduled > 0:
        issues.append("Misscheduled")

    severity = "healthy"
    if "NotReady" in issues:
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

def restart_daemonset(name: str, namespace: str = "default") -> dict:
    """
    Trigger a rolling restart of all pods in a DaemonSet.

    Uses the same annotation-patch mechanism as `kubectl rollout restart`.
    Pods are restarted sequentially across all nodes.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      DaemonSet name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "daemonset_name")
    namespace = validate_namespace(namespace)
    
    apps: AppsV1Api = get_apps_v1()
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
        apps.patch_namespaced_daemon_set(name=name, namespace=namespace, body=patch_body)
        logger.info(f"[ACTION] Rolling restart triggered for DaemonSet {namespace}/{name}")
        return {
            "success": True,
            "message": f"Rolling restart triggered for DaemonSet {namespace}/{name}.",
        }
    except ApiException as e:
        logger.error(f"Failed to restart DaemonSet {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def update_daemonset_image(
    name: str,
    namespace: str = "default",
    container: str = None,
    image: str = None,
) -> dict:
    """
    Update the image of a container in a DaemonSet's pod template.

    ⚠️  ACTION — requires user approval.

    Args:
        name:       DaemonSet name
        namespace:  Namespace
        container:  Container name to update
        image:      New image URI (e.g., "myapp:v1.2.3")

    Returns:
        {"success": bool, "message": str, "previous_image": str, "new_image": str}
    """
    # Input validation
    name = sanitize_input(name, "daemonset_name")
    namespace = validate_namespace(namespace)
    if container:
        container = sanitize_input(container, "container_name")
    if image:
        image = sanitize_input(image, "image_uri")
    
    if not container or not image:
        return {"success": False, "message": "container and image parameters are required."}

    apps: AppsV1Api = get_apps_v1()
    try:
        ds = apps.read_namespaced_daemon_set(name=name, namespace=namespace)
        
        containers = ds.spec.template.spec.containers
        found = False
        previous_image = None
        
        for c in containers:
            if c.name == container:
                previous_image = c.image
                c.image = image
                found = True
                break
        
        if not found:
            return {"success": False, "message": f"Container '{container}' not found in DaemonSet."}
        
        apps.patch_namespaced_daemon_set(name=name, namespace=namespace, body=ds)
        logger.info(f"[ACTION] Updated DaemonSet {namespace}/{name} container '{container}': {previous_image} → {image}")
        
        return {
            "success":         True,
            "message":         f"Container '{container}' in DaemonSet {namespace}/{name} updated.",
            "previous_image":  previous_image,
            "new_image":       image,
        }
    except ApiException as e:
        logger.error(f"Failed to update DaemonSet {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_daemonset(ds) -> dict:
    """Convert a raw DaemonSet object into a clean summary dict."""
    creation = ds.metadata.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    # Container images
    containers = []
    if ds.spec.template.spec.containers:
        for c in ds.spec.template.spec.containers:
            containers.append({
                "name":  c.name,
                "image": c.image,
                "ready": c.ready if hasattr(c, 'ready') else None,
            })

    status = ds.status  # K8s object, not a dict

    return {
        "name":                          ds.metadata.name,
        "namespace":                     ds.metadata.namespace,
        "desired_number_scheduled":      (status.desired_number_scheduled or 0) if status else 0,
        "current_number_scheduled":      (status.current_number_scheduled or 0) if status else 0,
        "number_ready":                  (status.number_ready or 0) if status else 0,
        "number_available":              (status.number_available or 0) if status else 0,
        "number_unavailable":            (status.number_unavailable or 0) if status else 0,
        "number_misscheduled":           (status.number_misscheduled or 0) if status else 0,
        "updated_number_scheduled":      (status.updated_number_scheduled or 0) if status else 0,
        "containers":                    containers,
        "selector":                      ds.spec.selector.match_labels or {},
        "node_selector":                 ds.spec.template.spec.node_selector or {},
        "age":                           age,
        "labels":                        ds.metadata.labels or {},
    }