"""
k8s_tools/namespaces.py

Namespace operations.

READ:
  - list_namespaces()                         → all namespaces
  - get_namespace(name)                       → single namespace detail
  - get_namespace_resource_count(namespace)   → count pods/deployments/services
"""

import logging
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1, get_apps_v1
from .utils import fmt_duration
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def list_namespaces() -> list[dict]:
    """
    List all namespaces in the cluster.

    Returns:
        List of namespace dicts with name, phase, age, resource counts.
    """
    core = get_core_v1()
    try:
        ns_list = core.list_namespace()
    except ApiException as e:
        logger.error(f"Failed to list namespaces: {e}")
        raise

    return [_summarize_namespace(ns) for ns in ns_list.items]


def get_namespace(name: str) -> dict:
    """Fetch a detailed summary for a single namespace."""
    core = get_core_v1()
    try:
        ns = core.read_namespace(name=name)
    except ApiException as e:
        logger.error(f"Namespace {name} not found: {e}")
        raise
    return _summarize_namespace(ns)


def get_namespace_resource_count(namespace: str) -> dict:
    """
    Count key resources in a namespace (pods, deployments, services, statefulsets, jobs).

    Useful for namespace health overview.
    """
    core = get_core_v1()
    apps = get_apps_v1()

    counts = {
        "pods": 0,
        "deployments": 0,
        "statefulsets": 0,
        "daemonsets": 0,
        "services": 0,
    }

    try:
        pods = core.list_namespaced_pod(namespace=namespace)
        counts["pods"] = len(pods.items)
    except ApiException as e:
        logger.warning(f"Could not count pods in {namespace}: {e}")

    try:
        deps = apps.list_namespaced_deployment(namespace=namespace)
        counts["deployments"] = len(deps.items)
    except ApiException as e:
        logger.warning(f"Could not count deployments in {namespace}: {e}")

    try:
        sfs = apps.list_namespaced_stateful_set(namespace=namespace)
        counts["statefulsets"] = len(sfs.items)
    except ApiException as e:
        logger.warning(f"Could not count statefulsets in {namespace}: {e}")

    try:
        dss = apps.list_namespaced_daemon_set(namespace=namespace)
        counts["daemonsets"] = len(dss.items)
    except ApiException as e:
        logger.warning(f"Could not count daemonsets in {namespace}: {e}")

    try:
        svcs = core.list_namespaced_service(namespace=namespace)
        counts["services"] = len(svcs.items)
    except ApiException as e:
        logger.warning(f"Could not count services in {namespace}: {e}")

    return counts


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_namespace(ns) -> dict:
    """Convert a raw Namespace object into a clean summary dict."""
    creation = ns.metadata.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    return {
        "name":   ns.metadata.name,
        "phase":  ns.status.phase if ns.status else "Unknown",
        "age":    age,
        "labels": ns.metadata.labels or {},
    }


def get_namespace_events(name: str, limit: int = 100) -> list[dict]:
    """Get recent events in the given namespace."""
    core = get_core_v1()
    try:
        events = core.list_namespaced_event(namespace=name, limit=limit)
    except ApiException as e:
        logger.error(f"Failed to fetch namespace events for {name}: {e}")
        raise

    rows = []
    for ev in events.items:
        rows.append(
            {
                "type": ev.type,
                "reason": ev.reason,
                "message": ev.message,
                "count": ev.count,
                "last_time": ev.last_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.last_timestamp else None,
                "involved_object": {
                    "kind": ev.involved_object.kind,
                    "name": ev.involved_object.name,
                },
            }
        )

    rows.sort(key=lambda e: (e["type"] == "Warning", e["last_time"] or ""), reverse=True)
    return rows
