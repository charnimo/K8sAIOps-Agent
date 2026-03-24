"""
k8s_client/nodes.py

Node-related read and action functions.

READ:
  - list_nodes()               → all nodes with status/conditions
  - get_node(name)             → single node detail
  - detect_node_issues(name)   → classify: MemoryPressure, DiskPressure, NotReady, etc.

ACTIONS (require user approval):
  - cordon_node(name)          → mark node unschedulable (new pods won't land here)
  - uncordon_node(name)        → re-enable scheduling
  - drain_node(name)           → cordon + evict all pods (dangerous, requires explicit approval)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1

logger = logging.getLogger(__name__)

# Known "bad" condition types for nodes
_BAD_CONDITIONS = {
    "MemoryPressure":   "True",   # True = bad
    "DiskPressure":     "True",
    "PIDPressure":      "True",
    "NetworkUnavailable": "True",
    "Ready":            "False",  # False = bad
}


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_nodes() -> list[dict]:
    """List all cluster nodes with status summaries."""
    core = get_core_v1()
    try:
        node_list = core.list_node()
    except ApiException as e:
        logger.error(f"Failed to list nodes: {e}")
        raise
    return [_summarize_node(n) for n in node_list.items]


def get_node(name: str) -> dict:
    """Fetch a detailed summary for a single node."""
    core = get_core_v1()
    try:
        node = core.read_node(name=name)
    except ApiException as e:
        logger.error(f"Node {name} not found: {e}")
        raise
    return _summarize_node(node)


def detect_node_issues(name: str) -> dict:
    """
    Detect problems on a specific node.

    Returns:
        {
          "issues": ["MemoryPressure", "NotReady"],
          "severity": "critical" | "warning" | "healthy",
          "details": { ... }
        }
    """
    summary = get_node(name)
    issues = []

    conditions = {c["type"]: c["status"] for c in summary.get("conditions", [])}

    for cond_type, bad_value in _BAD_CONDITIONS.items():
        if conditions.get(cond_type) == bad_value:
            label = "NotReady" if cond_type == "Ready" else cond_type
            issues.append(label)

    if summary.get("unschedulable"):
        issues.append("Cordoned")

    severity = "healthy"
    if "NotReady" in issues or "MemoryPressure" in issues or "DiskPressure" in issues:
        severity = "critical"
    elif issues:
        severity = "warning"

    return {
        "issues":   issues,
        "severity": severity,
        "details":  summary,
    }


def get_node_events(name: str) -> list[dict]:
    """Fetch events related to a specific node."""
    core = get_core_v1()
    try:
        event_list = core.list_event_for_all_namespaces(
            field_selector=f"involvedObject.name={name},involvedObject.kind=Node"
        )
    except ApiException as e:
        logger.error(f"Failed to fetch events for node {name}: {e}")
        raise

    events = []
    for ev in event_list.items:
        events.append({
            "type":      ev.type,
            "reason":    ev.reason,
            "message":   ev.message,
            "count":     ev.count,
            "last_time": ev.last_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.last_timestamp else None,
        })
    events.sort(key=lambda e: (e["type"] != "Warning", e["last_time"] or ""))
    return events


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def cordon_node(name: str) -> dict:
    """
    Mark a node as unschedulable (cordon).

    New pods will not be scheduled here. Existing pods are NOT evicted.

    ⚠️  ACTION — requires user approval.
    """
    core = get_core_v1()
    patch = {"spec": {"unschedulable": True}}
    try:
        core.patch_node(name=name, body=patch)
        logger.info(f"[ACTION] Cordoned node {name}")
        return {
            "success": True,
            "message": f"Node {name} cordoned. No new pods will be scheduled on it.",
        }
    except ApiException as e:
        logger.error(f"Failed to cordon node {name}: {e}")
        return {"success": False, "message": str(e)}


def uncordon_node(name: str) -> dict:
    """
    Re-enable scheduling on a previously cordoned node.

    ⚠️  ACTION — requires user approval.
    """
    core = get_core_v1()
    patch = {"spec": {"unschedulable": False}}
    try:
        core.patch_node(name=name, body=patch)
        logger.info(f"[ACTION] Uncordoned node {name}")
        return {
            "success": True,
            "message": f"Node {name} uncordoned. Scheduling is re-enabled.",
        }
    except ApiException as e:
        logger.error(f"Failed to uncordon node {name}: {e}")
        return {"success": False, "message": str(e)}


def drain_node(name: str, ignore_daemonsets: bool = True) -> dict:
    """
    Cordon a node and evict all evictable pods from it.

    ⚠️  DANGEROUS ACTION — permanently moves workloads off this node.
    ⚠️  DaemonSet pods are skipped by default (ignore_daemonsets=True).
    ⚠️  Requires explicit user approval.

    Note: This implementation cordons and then deletes non-DaemonSet pods.
    In production, use the kubectl drain logic with PodDisruptionBudget respect.
    """
    # Step 1: Cordon
    result = cordon_node(name)
    if not result["success"]:
        return result

    core = get_core_v1()
    evicted = []
    skipped = []

    try:
        # Find all pods on this node (across all namespaces)
        pods = core.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={name}"
        )
        for pod in pods.items:
            pod_name = pod.metadata.name
            pod_ns   = pod.metadata.namespace

            # Skip DaemonSet-owned pods if requested
            owners = pod.metadata.owner_references or []
            if ignore_daemonsets and any(o.kind == "DaemonSet" for o in owners):
                skipped.append(f"{pod_ns}/{pod_name} (DaemonSet)")
                continue

            try:
                core.delete_namespaced_pod(name=pod_name, namespace=pod_ns)
                evicted.append(f"{pod_ns}/{pod_name}")
                logger.info(f"[ACTION] Drained pod {pod_ns}/{pod_name} from node {name}")
            except ApiException as e:
                skipped.append(f"{pod_ns}/{pod_name} (error: {e.reason})")

    except ApiException as e:
        return {"success": False, "message": f"Failed to list pods on node {name}: {e}"}

    return {
        "success": True,
        "message": f"Node {name} drained.",
        "evicted": evicted,
        "skipped": skipped,
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_node(node) -> dict:
    info   = node.status.node_info if node.status else None
    alloc  = node.status.allocatable or {}
    cap    = node.status.capacity or {}

    conditions = []
    if node.status and node.status.conditions:
        for c in node.status.conditions:
            conditions.append({
                "type":    c.type,
                "status":  c.status,
                "reason":  c.reason,
                "message": c.message,
            })

    creation = node.metadata.creation_timestamp
    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        secs = int(delta.total_seconds())
        age = f"{secs // 86400}d" if secs >= 86400 else f"{secs // 3600}h"

    return {
        "name":              node.metadata.name,
        "unschedulable":     node.spec.unschedulable or False,
        "labels":            node.metadata.labels or {},
        "age":               age,
        "conditions":        conditions,
        "allocatable": {
            "cpu":    alloc.get("cpu"),
            "memory": alloc.get("memory"),
            "pods":   alloc.get("pods"),
        },
        "capacity": {
            "cpu":    cap.get("cpu"),
            "memory": cap.get("memory"),
            "pods":   cap.get("pods"),
        },
        "os":               info.os_image if info else None,
        "kernel":           info.kernel_version if info else None,
        "container_runtime": info.container_runtime_version if info else None,
        "kubelet_version":  info.kubelet_version if info else None,
    }
