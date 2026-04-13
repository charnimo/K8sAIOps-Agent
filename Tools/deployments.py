"""
tools/deployments.py

All Deployment-related read and action functions.

READ:
  - list_deployments(namespace)             → summary list
  - get_deployment(name, namespace)         → detailed summary
  - get_deployment_events(name, namespace)  → related events
  - rollout_status(name, namespace)         → check if rollout is complete
  - rollout_history(name, namespace)        → view revision history

ACTIONS (require user approval):
  - scale_deployment(name, namespace, replicas)          → set replica count
  - rollout_restart(name, namespace)                     → rolling restart
  - rollback_deployment(name, namespace, revision)       → revert to previous version
  - patch_resource_limits(name, namespace, container, …) → update CPU/memory limits
  - patch_env_var(name, namespace, container, key, val)  → update an env variable
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client
from kubernetes.client import AppsV1Api
from kubernetes.client.exceptions import ApiException

from .client import get_apps_v1, get_core_v1
from .utils import fmt_duration, fmt_time, retry_on_transient, validate_namespace, validate_replicas, sanitize_input, validate_resource_limits
from .events import sort_events
from .audit import audit_deployment_scale, audit_rollout_restart, audit_patch_resource_limits, audit_patch_env_var, log_action

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_deployments(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """List deployments in a namespace with key status fields.
    
    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector (e.g., "app=web")
    """
    apps: AppsV1Api = get_apps_v1()
    try:
        dep_list = apps.list_namespaced_deployment(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list deployments in {namespace}: {e}")
        raise
    return [_summarize_deployment(d) for d in dep_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_all_deployments(label_selector: Optional[str] = None) -> list[dict]:
    """List deployments across ALL namespaces.
    
    Args:
        label_selector: Optional Kubernetes label selector
    """
    apps: AppsV1Api = get_apps_v1()
    try:
        dep_list = apps.list_deployment_for_all_namespaces(label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list all deployments: {e}")
        raise
    return [_summarize_deployment(d) for d in dep_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_deployment(name: str, namespace: str = "default") -> dict:
    """Fetch a full summary for a specific deployment."""
    apps: AppsV1Api = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Deployment {namespace}/{name} not found: {e}")
        raise
    return _summarize_deployment(dep)


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_deployment_events(name: str, namespace: str = "default") -> list[dict]:
    """Fetch events related to a specific deployment (and its ReplicaSets)."""
    core = get_core_v1()
    try:
        event_list = core.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={name},involvedObject.kind=Deployment",
        )
    except ApiException as e:
        logger.error(f"Failed to fetch events for deployment {namespace}/{name}: {e}")
        raise

    events = []
    for ev in event_list.items:
        events.append({
            "type":       ev.type,
            "reason":     ev.reason,
            "message":    ev.message,
            "count":      ev.count,
            "last_time":  fmt_time(ev.last_timestamp),
        })
    return sort_events(events)


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def scale_deployment(
    name: str,
    namespace: str = "default",
    replicas: int = 1,
) -> dict:
    """
    Scale a deployment to the given replica count.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Deployment name
        namespace: Namespace
        replicas:  Desired replica count (must be >= 0)

    Returns:
        {"success": bool, "message": str, "previous_replicas": int, "new_replicas": int}
    """
    # Input validation
    try:
        name = sanitize_input(name, "deployment_name")
        namespace = validate_namespace(namespace)
        replicas = validate_replicas(replicas)
    except ValueError as e:
        return {"success": False, "message": f"Invalid input: {str(e)}"}

    apps: AppsV1Api = get_apps_v1()
    
    # Defensive check: verify deployment exists before scaling
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {"success": False, "message": f"Deployment {namespace}/{name} not found"}
        raise
    
    try:
        previous = dep.spec.replicas

        dep.spec.replicas = replicas
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=dep)

        logger.info(f"[ACTION] Scaled {namespace}/{name}: {previous} → {replicas} replicas")
        audit_deployment_scale(name, namespace, replicas, success=True)
        return {
            "success":           True,
            "message":           f"Deployment {namespace}/{name} scaled from {previous} to {replicas} replicas.",
            "previous_replicas": previous,
            "new_replicas":      replicas,
        }
    except ApiException as e:
        logger.error(f"Failed to scale {namespace}/{name}: {e}")
        audit_deployment_scale(name, namespace, replicas, success=False, error=str(e))
        return {"success": False, "message": str(e)}


def rollout_restart(name: str, namespace: str = "default") -> dict:
    """
    Trigger a rolling restart of all pods in a deployment.

    Implemented by patching the pod template annotation with the current timestamp,
    which causes Kubernetes to perform a rolling update.

    ⚠️  ACTION — requires user approval.
    """
    # Input validation
    name = sanitize_input(name, "deployment_name")
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
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=patch_body)
        logger.info(f"[ACTION] Rolling restart triggered for {namespace}/{name}")
        audit_rollout_restart(name, namespace, "Deployment", success=True)
        return {
            "success": True,
            "message": f"Rolling restart triggered for deployment {namespace}/{name}.",
        }
    except ApiException as e:
        logger.error(f"Failed to restart {namespace}/{name}: {e}")
        audit_rollout_restart(name, namespace, "Deployment", success=False, error=str(e))
        return {"success": False, "message": str(e)}

def get_deployment_revisions(name: str, namespace: str = "default") -> dict:
    """
    List all available revision history for a Deployment.

    Each revision is a snapshot of a past ReplicaSet. Use this to inspect
    what versions are available before performing a rollback.

    For actual rollback, use: kubectl rollout undo deployment/NAME [--to-revision=N]
    The Python SDK does not support rollout undo directly, so rollback requires CLI.

    Args:
        name:      Deployment name
        namespace: Namespace

    Returns:
        {
          "current_revision": int,
          "revisions": [
              {"revision": int, "replica_set": "name-abc123", "replicas": int, "age": "2 hours"}
          ]
        }
    """
    apps: AppsV1Api = get_apps_v1()

    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
        current_rev = int(dep.metadata.annotations.get("deployment.kubernetes.io/revision", "0") if dep.metadata.annotations else "0")

        # Find all ReplicaSets owned by this Deployment
        rs_list = apps.list_namespaced_replica_set(namespace=namespace)

        revisions = []
        for rs in rs_list.items:
            if rs.metadata.owner_references:
                for owner in rs.metadata.owner_references:
                    if owner.kind == "Deployment" and owner.name == name:
                        rev_str = rs.metadata.annotations.get("deployment.kubernetes.io/revision", "0") if rs.metadata.annotations else "0"
                        try:
                            rev_num = int(rev_str)
                            age_seconds = (datetime.now(timezone.utc) - rs.metadata.creation_timestamp.replace(tzinfo=timezone.utc)).total_seconds()
                            revisions.append({
                                "revision": rev_num,
                                "replica_set": rs.metadata.name,
                                "replicas": rs.spec.replicas or 0,
                                "age": fmt_duration(int(age_seconds)),
                                "ready": rs.status.ready_replicas or 0,
                            })
                        except (ValueError, AttributeError):
                            pass
                        break

        # Sort by revision descending (newest first)
        revisions.sort(key=lambda x: x["revision"], reverse=True)

        return {
            "success": True,
            "current_revision": current_rev,
            "revisions": revisions,
            "message": f"Found {len(revisions)} revision(s) for deployment {namespace}/{name}",
        }
    except ApiException as e:
        logger.error(f"Failed to list revisions for {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}
 
 

def patch_resource_limits(
    name: str,
    namespace: str = "default",
    container_name: Optional[str] = None,
    cpu_request: Optional[str] = None,
    cpu_limit: Optional[str] = None,
    memory_request: Optional[str] = None,
    memory_limit: Optional[str] = None,
) -> dict:
    """
    Patch CPU and/or memory requests/limits for a container in a deployment.

    ⚠️  ACTION — requires user approval.

    Args:
        name:             Deployment name
        namespace:        Namespace
        container_name:   Container to patch (auto-detected if only one container)
        cpu_request:      e.g. "250m"
        cpu_limit:        e.g. "500m"
        memory_request:   e.g. "256Mi"
        memory_limit:     e.g. "512Mi"

    Returns:
        {"success": bool, "message": str, "changes": dict}
    """
    # Input validation
    name = sanitize_input(name, "deployment_name")
    namespace = validate_namespace(namespace)
    if container_name:
        container_name = sanitize_input(container_name, "container_name")
    
    apps: AppsV1Api = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        return {"success": False, "message": f"Deployment not found: {e}"}

    containers = dep.spec.template.spec.containers
    if not containers:
        return {"success": False, "message": "No containers found in deployment spec."}

    # Resolve target container
    target = None
    if container_name:
        target = next((c for c in containers if c.name == container_name), None)
        if not target:
            return {"success": False, "message": f"Container '{container_name}' not found."}
    elif len(containers) == 1:
        target = containers[0]
    else:
        names = [c.name for c in containers]
        return {"success": False, "message": f"Multiple containers found; specify container_name: {names}"}

    # Build patch
    if target.resources is None:
        target.resources = client.V1ResourceRequirements()
    if target.resources.requests is None:
        target.resources.requests = {}
    if target.resources.limits is None:
        target.resources.limits = {}

    changes = {}
    if cpu_request:
        target.resources.requests["cpu"] = cpu_request
        changes["cpu_request"] = cpu_request
    if cpu_limit:
        target.resources.limits["cpu"] = cpu_limit
        changes["cpu_limit"] = cpu_limit
    if memory_request:
        target.resources.requests["memory"] = memory_request
        changes["memory_request"] = memory_request
    if memory_limit:
        target.resources.limits["memory"] = memory_limit
        changes["memory_limit"] = memory_limit

    if not changes:
        return {"success": False, "message": "No resource changes specified."}

    try:
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=dep)
        logger.info(f"[ACTION] Patched resources for {namespace}/{name}/{target.name}: {changes}")
        audit_patch_resource_limits(name, namespace, target.name, changes, success=True)
        return {
            "success": True,
            "message": f"Resource limits updated for container '{target.name}' in {namespace}/{name}.",
            "changes": changes,
        }
    except ApiException as e:
        logger.error(f"Failed to patch resources for {namespace}/{name}: {e}")
        audit_patch_resource_limits(name, namespace, target.name, changes, success=False, error=str(e))
        return {"success": False, "message": str(e)}


def patch_env_var(
    name: str,
    namespace: str = "default",
    container_name: Optional[str] = None,
    key: str = "",
    value: str = "",
) -> dict:
    """
    Add or update an environment variable in a deployment's container spec.

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str, "action": "added" | "updated"}
    """
    # Input validation
    name = sanitize_input(name, "deployment_name")
    namespace = validate_namespace(namespace)
    if container_name:
        container_name = sanitize_input(container_name, "container_name")
    
    if not key:
        return {"success": False, "message": "Environment variable key must not be empty."}
    
    key = sanitize_input(key, "env_key")
    value = sanitize_input(value, "env_value")

    apps: AppsV1Api = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        return {"success": False, "message": f"Deployment not found: {e}"}

    containers = dep.spec.template.spec.containers
    target = None
    if container_name:
        target = next((c for c in containers if c.name == container_name), None)
    elif len(containers) == 1:
        target = containers[0]
    else:
        return {"success": False, "message": f"Specify container_name. Found: {[c.name for c in containers]}"}

    if not target:
        return {"success": False, "message": f"Container '{container_name}' not found."}

    if target.env is None:
        target.env = []

    action = "added"
    for env in target.env:
        if env.name == key:
            env.value = value
            action = "updated"
            break
    else:
        target.env.append(client.V1EnvVar(name=key, value=value))

    try:
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=dep)
        logger.info(f"[ACTION] {action.capitalize()} env var {key} in {namespace}/{name}/{target.name}")
        audit_patch_env_var(name, namespace, target.name, key, success=True)
        return {
            "success": True,
            "message": f"Environment variable '{key}' {action} in container '{target.name}' of {namespace}/{name}.",
            "action":  action,
        }
    except ApiException as e:
        logger.error(f"Failed to patch env var in {namespace}/{name}: {e}")
        audit_patch_env_var(name, namespace, target.name, key, success=False, error=str(e))
        return {"success": False, "message": str(e)}


def rollout_status(name: str, namespace: str = "default") -> dict:
    """
    Check the status of a Deployment rollout.

    Returns current and desired replicas, ready replicas, and rollout progress.

    Returns:
        {
          "name": "my-deployment",
          "namespace": "default",
          "status": "progressing" | "complete" | "failed",
          "desired": 3,
          "current": 3,
          "ready": 2,
          "updated": 2,
          "available": 2,
          "message": "Rollout complete. 2 of 3 pods ready."
        }
    """
    apps = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to get Deployment {namespace}/{name}: {e}")
        return {"error": str(e)}

    spec = dep.spec
    status = dep.status or {}

    desired = spec.replicas or 1
    current = status.current_replicas or 0
    ready = status.ready_replicas or 0
    updated = status.updated_replicas or 0
    available = status.available_replicas or 0

    # Determine rollout status
    if ready == desired and available == desired:
        status_str = "complete"
        message = f"Rollout complete. {ready} of {desired} pods ready."
    elif status.conditions:
        # Check for failure conditions
        for cond in status.conditions:
            if cond.type == "Progressing" and cond.reason == "ProgressDeadlineExceeded":
                status_str = "failed"
                message = f"Rollout failed: {cond.message}"
                break
        else:
            status_str = "progressing"
            message = f"Rollout in progress. {ready} of {desired} pods ready."
    else:
        status_str = "progressing" if ready < desired else "complete"
        message = f"{ready} of {desired} pods ready."

    return {
        "name": dep.metadata.name,
        "namespace": dep.metadata.namespace,
        "status": status_str,
        "desired": desired,
        "current": current,
        "ready": ready,
        "updated": updated,
        "available": available,
        "message": message,
    }


def rollout_history(name: str, namespace: str = "default") -> dict:
    """
    Get Deployment revision history.

    Returns list of recent revisions (from ReplicaSets).

    Returns:
        {
          "name": "my-deployment",
          "namespace": "default",
          "revisions": [
            {"revision": 3, "image": "app:v1.3", "created": "2026-04-11T10:00:00Z", "replicas": 3},
            {"revision": 2, "image": "app:v1.2", "created": "2026-04-11T09:00:00Z", "replicas": 0},
          ]
        }
    """
    apps = get_apps_v1()

    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)

        # List ReplicaSets (which track revisions)
        rs_list = apps.list_namespaced_replica_set(
            namespace=namespace,
            label_selector=f"app={dep.spec.selector.match_labels.get('app', 'unknown')}"
        )

        revisions = []
        for rs in rs_list.items:
            # Extract revision from ReplicaSet
            revision_label = rs.metadata.annotations.get("deployment.kubernetes.io/revision", "?") if rs.metadata.annotations else "?"

            # Get image from ReplicaSet pod template
            image = "N/A"
            if rs.spec.template.spec.containers:
                image = rs.spec.template.spec.containers[0].image

            revisions.append({
                "revision": revision_label,
                "image": image,
                "created": fmt_time(rs.metadata.creation_timestamp),
                "replicas": rs.status.replicas or 0,
            })

        # Sort by revision (descending)
        revisions.sort(key=lambda x: int(x.get("revision", 0)) if str(x.get("revision", 0)).isdigit() else 0, reverse=True)

        return {
            "name": dep.metadata.name,
            "namespace": dep.metadata.namespace,
            "revisions": revisions,
        }
    except ApiException as e:
        logger.error(f"Failed to get rollout history for {namespace}/{name}: {e}")
        return {"error": str(e)}


def rollback_deployment(name: str, namespace: str = "default", revision: Optional[int] = None) -> dict:
    """
    Rollback a Deployment to a previous revision.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Deployment name
        namespace: Namespace
        revision:  Specific revision to rollback to (0 = previous, optional)

    Returns:
        {"success": bool, "message": str, "previous_revision": int, "new_revision": int}
    """
    apps = get_apps_v1()

    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
        current_revision = int(
            dep.metadata.annotations.get("deployment.kubernetes.io/revision", "0")
            if dep.metadata.annotations else "0"
        )

        # Build rollback body
        if revision is None:
            rollback_body = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": name, "namespace": namespace},
                "spec": {"template": dep.spec.template}  # Revert to current template (no-op)
            }
        else:
            # Get the specific revision from ReplicaSet history
            rs_list = apps.list_namespaced_replica_set(namespace=namespace)
            target_rs = None
            for rs in rs_list.items:
                rs_revision = int(
                    rs.metadata.annotations.get("deployment.kubernetes.io/revision", "0")
                    if rs.metadata.annotations else "0"
                )
                if rs_revision == revision:
                    target_rs = rs
                    break

            if not target_rs:
                return {"success": False, "message": f"Revision {revision} not found."}

            # Revert to the target ReplicaSet's pod template
            rollback_body = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": name, "namespace": namespace},
                "spec": {"template": target_rs.spec.template}
            }

        # Apply rollback (this triggers a rolling update to the old spec)
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=rollback_body)

        logger.info(f"[ACTION] Rolled back Deployment {namespace}/{name} from revision {current_revision} to {revision or 'previous'}")
        log_action(
            "deployment_rollback",
            name,
            namespace,
            success=True,
            details={"from_revision": current_revision, "to_revision": revision or "previous"},
        )

        return {
            "success": True,
            "message": f"Deployment {namespace}/{name} rolled back.",
            "previous_revision": current_revision,
            "new_revision": revision or current_revision - 1,
        }
    except ApiException as e:
        logger.error(f"Failed to rollback Deployment {namespace}/{name}: {e}")
        log_action(
            "deployment_rollback",
            name,
            namespace,
            success=False,
            error_message=str(e),
        )
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_deployment(dep) -> dict:
    status = dep.status
    spec = dep.spec
    creation = dep.metadata.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        secs = int(delta.total_seconds())
        age = fmt_duration(secs)

    # Container resource specs
    containers_info = []
    if spec and spec.template and spec.template.spec:
        for c in spec.template.spec.containers:
            res = {}
            if c.resources:
                res["requests"] = {}
                res["limits"] = {}
                if c.resources.requests:
                    res["requests"] = dict(c.resources.requests)
                if c.resources.limits:
                    res["limits"] = dict(c.resources.limits)
            containers_info.append({
                "name":      c.name,
                "image":     c.image,
                "resources": res,
            })

    return {
        "name":                dep.metadata.name,
        "namespace":           dep.metadata.namespace,
        "replicas":            spec.replicas if spec else None,
        "ready_replicas":      status.ready_replicas if status else 0,
        "available_replicas":  status.available_replicas if status else 0,
        "updated_replicas":    status.updated_replicas if status else 0,
        "age":                 age,
        "labels":              dep.metadata.labels or {},
        "selector":            spec.selector.match_labels if spec and spec.selector else {},
        "containers":          containers_info,
        "strategy":            spec.strategy.type if spec and spec.strategy else None,
    }
