"""
tools/pods.py

All pod-related read and action functions.

READ functions:
  - list_pods(namespace)               → list all pods in a namespace
  - get_pod(name, namespace)           → get a single pod object
  - get_pod_status(name, namespace)    → summarized status dict
  - get_pod_logs(name, namespace, ...)  → fetch logs (current or previous)
  - get_pod_events(name, namespace)    → events related to a specific pod
  - detect_pod_issues(name, namespace) → classify what's wrong with a pod

ACTION functions (all require explicit approval in the agent layer):
  - delete_pod(name, namespace)        → force-restart by deleting (ReplicaSet recreates)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException

from .client import get_core_v1
from .utils import fmt_time, fmt_duration
from .events import _sort_events

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_pods(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List pods in a namespace with their key status fields.

    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector (e.g., "app=web,tier=frontend")

    Returns a list of dicts with:
      name, namespace, phase, ready, restarts, node, age, conditions, containers
    """
    core: CoreV1Api = get_core_v1()
    try:
        pod_list = core.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list pods in {namespace}: {e}")
        raise

    result = []
    for pod in pod_list.items:
        result.append(_summarize_pod(pod))
    return result


def list_all_pods(label_selector: Optional[str] = None) -> list[dict]:
    """List pods across ALL namespaces.
    
    Args:
        label_selector: Optional Kubernetes label selector
    """
    core: CoreV1Api = get_core_v1()
    try:
        pod_list = core.list_pod_for_all_namespaces(label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list all pods: {e}")
        raise
    return [_summarize_pod(pod) for pod in pod_list.items]


def get_pod(name: str, namespace: str = "default"):
    """Fetch the raw Kubernetes Pod object."""
    core: CoreV1Api = get_core_v1()
    try:
        return core.read_namespaced_pod(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Pod {namespace}/{name} not found: {e}")
        raise


def get_pod_status(name: str, namespace: str = "default") -> dict:
    """
    Return a detailed status summary for a single pod.

    Includes phase, conditions, container states, restart counts.
    """
    pod = get_pod(name, namespace)
    return _summarize_pod(pod)


def get_pod_status_with_metrics(name: str, namespace: str = "default") -> dict:
    """
    Return pod status enriched with current resource usage metrics.

    Combines pod phase/conditions with live CPU/memory usage from Metrics Server.
    
    Returns:
        {
          ...pod_status fields...,
          "containers": [
            {
              "name": "app",
              "ready": true,
              "restart_count": 0,
              "state": {...},
              "resources": {
                "requests": {"cpu": "100m", "memory": "256Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
                "usage": {"cpu": "45m", "memory": "256Mi"},
                "usage_pct": {"cpu": 9.0, "memory": 50.0}
              }
            }
          ]
        }
    """
    from .metrics import get_pod_metrics
    from .utils import parse_memory_mi, parse_cpu_m
    
    status = get_pod_status(name, namespace)
    metrics = get_pod_metrics(name, namespace)
    
    # If no metrics available, return status as-is
    if "error" in metrics:
        return status
    
    # Enrich each container with usage and usage percentages
    enriched_containers = []
    metrics_by_name = {c["name"]: c for c in metrics.get("containers", [])}
    
    for container in status.get("containers", []):
        cname = container["name"]
        container_copy = dict(container)
        
        # Build resources dict with requests, limits, and usage
        res_spec = container_copy.get("resources", {})
        if res_spec:
            usage_data = metrics_by_name.get(cname, {})
            
            # Calculate usage percentages
            usage_pct = {}
            
            # Memory percentage
            mem_limit = res_spec.get("limits", {}).get("memory")
            if mem_limit and usage_data.get("memory"):
                mem_limit_mi = parse_memory_mi(mem_limit)
                mem_usage_mi = parse_memory_mi(usage_data["memory"])
                if mem_limit_mi > 0:
                    usage_pct["memory"] = round((mem_usage_mi / mem_limit_mi) * 100, 1)
            
            # CPU percentage
            cpu_limit = res_spec.get("limits", {}).get("cpu")
            if cpu_limit and usage_data.get("cpu"):
                cpu_limit_m = parse_cpu_m(cpu_limit)
                cpu_usage_m = parse_cpu_m(usage_data["cpu"])
                if cpu_limit_m > 0:
                    usage_pct["cpu"] = round((cpu_usage_m / cpu_limit_m) * 100, 1)
            
            # Add usage data to resources
            container_copy["resources"]["usage"] = {
                "cpu": usage_data.get("cpu"),
                "memory": usage_data.get("memory"),
            }
            if usage_pct:
                container_copy["resources"]["usage_pct"] = usage_pct
        
        enriched_containers.append(container_copy)
    
    status["containers"] = enriched_containers
    return status


def get_pod_logs(
    name: str,
    namespace: str = "default",
    container: Optional[str] = None,
    previous: bool = False,
    tail_lines: int = 100,
) -> str:
    """
    Fetch logs from a pod container.

    Args:
        name:       Pod name
        namespace:  Namespace
        container:  Container name (auto-detected if pod has only one)
        previous:   If True, fetch logs from the previous (crashed) container instance
        tail_lines: Number of lines to return from the end

    Returns:
        Log string (may be empty if container hasn't started)
    """
    core: CoreV1Api = get_core_v1()
    try:
        logs = core.read_namespaced_pod_log(
            name=name,
            namespace=namespace,
            container=container,
            previous=previous,
            tail_lines=tail_lines,
            timestamps=True,
        )
        return logs
    except ApiException as e:
        # 400 often means the container hasn't started yet
        logger.warning(f"Could not fetch logs for {namespace}/{name}: {e.reason}")
        return f"[Log unavailable: {e.reason}]"


def get_pod_events(name: str, namespace: str = "default") -> list[dict]:
    """
    Fetch Kubernetes events related to a specific pod.

    Returns a list of event dicts sorted by timestamp (newest first).
    """
    core: CoreV1Api = get_core_v1()
    try:
        event_list = core.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={name},involvedObject.kind=Pod",
        )
    except ApiException as e:
        logger.error(f"Failed to fetch events for pod {namespace}/{name}: {e}")
        raise

    events = []
    for ev in event_list.items:
        events.append({
            "type":    ev.type,           # Normal / Warning
            "reason":  ev.reason,
            "message": ev.message,
            "count":   ev.count,
            "first_time": fmt_time(ev.first_timestamp),
            "last_time":  fmt_time(ev.last_timestamp),
        })

    return _sort_events(events)


def detect_pod_issues(name: str, namespace: str = "default") -> dict:
    """
    Classify what is wrong with a pod.

    Returns:
        {
          "issues": ["CrashLoopBackOff", "OOMKilled"],   # list of detected issue types
          "severity": "critical" | "warning" | "healthy",
          "details": { ... }                              # raw data that led to this conclusion
        }

    Issue types that can be detected:
      CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending,
      Evicted, HighRestartCount, NotReady, Unknown
    """
    pod = get_pod(name, namespace)
    summary = _summarize_pod(pod)
    issues = []

    phase = summary.get("phase", "")
    if phase == "Pending":
        issues.append("Pending")
    if phase == "Unknown":
        issues.append("Unknown")

    # Check each container
    for container in summary.get("containers", []):
        state = container.get("state", {})
        waiting = state.get("waiting", {})
        terminated = state.get("terminated", {})

        reason = waiting.get("reason", "") or terminated.get("reason", "")

        if reason == "CrashLoopBackOff":
            issues.append("CrashLoopBackOff")
        if reason in ("ImagePullBackOff", "ErrImagePull"):
            issues.append("ImagePullBackOff")
        if terminated.get("reason") == "OOMKilled":
            issues.append("OOMKilled")

        restarts = container.get("restart_count", 0)
        if restarts >= 5:
            issues.append("HighRestartCount")

    if not summary.get("ready") and phase == "Running":
        issues.append("NotReady")

    # Deduplicate
    issues = list(dict.fromkeys(issues))

    severity = "healthy"
    if any(i in issues for i in ["CrashLoopBackOff", "OOMKilled", "ImagePullBackOff", "Evicted"]):
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

def delete_pod(name: str, namespace: str = "default") -> dict:
    """
    Delete a pod to force a restart (only safe if managed by a ReplicaSet/Deployment).

    ⚠️  This is an ACTION — must be called only after user approval in the agent layer.

    Returns: {"success": True/False, "message": str}
    """
    core: CoreV1Api = get_core_v1()
    try:
        core.delete_namespaced_pod(name=name, namespace=namespace)
        logger.info(f"[ACTION] Deleted pod {namespace}/{name} to force restart")
        return {"success": True, "message": f"Pod {namespace}/{name} deleted. It will be recreated by its controller."}
    except ApiException as e:
        logger.error(f"Failed to delete pod {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

def _summarize_pod(pod) -> dict:
    """Convert a raw Pod object into a clean summary dict."""
    name = pod.metadata.name
    namespace = pod.metadata.namespace
    phase = pod.status.phase if pod.status else "Unknown"
    node = pod.spec.node_name if pod.spec else None
    creation = pod.metadata.creation_timestamp

    # Age
    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    # Conditions
    conditions = []
    if pod.status and pod.status.conditions:
        for cond in pod.status.conditions:
            conditions.append({
                "type":   cond.type,
                "status": cond.status,
                "reason": cond.reason,
            })

    # Ready check
    ready = any(
        c["type"] == "Ready" and c["status"] == "True"
        for c in conditions
    )

    # Container statuses
    containers = []
    if pod.status and pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            state_dict = {}
            if cs.state:
                if cs.state.running:
                    state_dict["running"] = {"started_at": fmt_time(cs.state.running.started_at)}
                if cs.state.waiting:
                    state_dict["waiting"] = {
                        "reason":  cs.state.waiting.reason,
                        "message": cs.state.waiting.message,
                    }
                if cs.state.terminated:
                    state_dict["terminated"] = {
                        "reason":    cs.state.terminated.reason,
                        "exit_code": cs.state.terminated.exit_code,
                        "message":   cs.state.terminated.message,
                    }
            containers.append({
                "name":          cs.name,
                "ready":         cs.ready,
                "restart_count": cs.restart_count,
                "state":         state_dict,
            })

    # Resource requests/limits from spec
    resource_specs = []
    if pod.spec and pod.spec.containers:
        for c in pod.spec.containers:
            res = {}
            if c.resources:
                res["requests"] = {
                    "cpu":    c.resources.requests.get("cpu") if c.resources.requests else None,
                    "memory": c.resources.requests.get("memory") if c.resources.requests else None,
                }
                res["limits"] = {
                    "cpu":    c.resources.limits.get("cpu") if c.resources.limits else None,
                    "memory": c.resources.limits.get("memory") if c.resources.limits else None,
                }
            resource_specs.append({"name": c.name, "resources": res})

    return {
        "name":           name,
        "namespace":      namespace,
        "phase":          phase,
        "ready":          ready,
        "node":           node,
        "age":            age,
        "conditions":     conditions,
        "containers":     containers,
        "resource_specs": resource_specs,
        "labels":         pod.metadata.labels or {},
    }
