"""
k8s_client/deployments.py

All Deployment-related read and action functions.

READ:
  - list_deployments(namespace)             → summary list
  - get_deployment(name, namespace)         → detailed summary
  - get_deployment_events(name, namespace)  → related events

ACTIONS (require user approval):
  - scale_deployment(name, namespace, replicas)          → set replica count
  - rollout_restart(name, namespace)                     → rolling restart
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
from .utils import fmt_duration

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_deployments(namespace: str = "default") -> list[dict]:
    """List all deployments in a namespace with key status fields."""
    apps: AppsV1Api = get_apps_v1()
    try:
        dep_list = apps.list_namespaced_deployment(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list deployments in {namespace}: {e}")
        raise
    return [_summarize_deployment(d) for d in dep_list.items]


def list_all_deployments() -> list[dict]:
    """List deployments across ALL namespaces."""
    apps: AppsV1Api = get_apps_v1()
    try:
        dep_list = apps.list_deployment_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all deployments: {e}")
        raise
    return [_summarize_deployment(d) for d in dep_list.items]


def get_deployment(name: str, namespace: str = "default") -> dict:
    """Fetch a full summary for a specific deployment."""
    apps: AppsV1Api = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Deployment {namespace}/{name} not found: {e}")
        raise
    return _summarize_deployment(dep)


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
            "last_time":  ev.last_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.last_timestamp else None,
        })
    events.sort(key=lambda e: (e["type"] != "Warning", e["last_time"] or ""))
    return events


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
    if replicas < 0:
        return {"success": False, "message": "Replica count cannot be negative."}

    apps: AppsV1Api = get_apps_v1()
    try:
        dep = apps.read_namespaced_deployment(name=name, namespace=namespace)
        previous = dep.spec.replicas

        dep.spec.replicas = replicas
        apps.patch_namespaced_deployment(name=name, namespace=namespace, body=dep)

        logger.info(f"[ACTION] Scaled {namespace}/{name}: {previous} → {replicas} replicas")
        return {
            "success":           True,
            "message":           f"Deployment {namespace}/{name} scaled from {previous} to {replicas} replicas.",
            "previous_replicas": previous,
            "new_replicas":      replicas,
        }
    except ApiException as e:
        logger.error(f"Failed to scale {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def rollout_restart(name: str, namespace: str = "default") -> dict:
    """
    Trigger a rolling restart of all pods in a deployment.

    Implemented by patching the pod template annotation with the current timestamp,
    which causes Kubernetes to perform a rolling update.

    ⚠️  ACTION — requires user approval.
    """
    apps: AppsV1Api = get_apps_v1()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        return {
            "success": True,
            "message": f"Rolling restart triggered for deployment {namespace}/{name}.",
        }
    except ApiException as e:
        logger.error(f"Failed to restart {namespace}/{name}: {e}")
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
        return {
            "success": True,
            "message": f"Resource limits updated for container '{target.name}' in {namespace}/{name}.",
            "changes": changes,
        }
    except ApiException as e:
        logger.error(f"Failed to patch resources for {namespace}/{name}: {e}")
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
    if not key:
        return {"success": False, "message": "Environment variable key must not be empty."}

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
        return {
            "success": True,
            "message": f"Environment variable '{key}' {action} in container '{target.name}' of {namespace}/{name}.",
            "action":  action,
        }
    except ApiException as e:
        logger.error(f"Failed to patch env var in {namespace}/{name}: {e}")
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
