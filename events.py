"""
k8s_client/events.py

Kubernetes event collection functions.

READ:
  - list_events(namespace)           → recent events in a namespace
  - list_all_events()                → events cluster-wide
  - list_warning_events(namespace)   → only Warning-type events
  - get_events_for_resource(name, kind, namespace) → events for any resource
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1

logger = logging.getLogger(__name__)


def list_events(namespace: str = "default", limit: int = 100) -> list[dict]:
    """
    List recent events in a namespace, sorted by last timestamp descending.

    Args:
        namespace: Target namespace
        limit:     Max events to return

    Returns:
        List of event dicts with type, reason, message, involved object, etc.
    """
    core = get_core_v1()
    try:
        event_list = core.list_namespaced_event(
            namespace=namespace,
            limit=limit,
        )
    except ApiException as e:
        logger.error(f"Failed to list events in {namespace}: {e}")
        raise

    return _sort_events([_fmt_event(ev) for ev in event_list.items])


def list_all_events(limit: int = 200) -> list[dict]:
    """
    List events across ALL namespaces.

    Returns events sorted with Warnings first, then by recency.
    """
    core = get_core_v1()
    try:
        event_list = core.list_event_for_all_namespaces(limit=limit)
    except ApiException as e:
        logger.error(f"Failed to list all events: {e}")
        raise
    return _sort_events([_fmt_event(ev) for ev in event_list.items])


def list_warning_events(namespace: Optional[str] = None, limit: int = 100) -> list[dict]:
    """
    Return only Warning-type events (the ones that actually matter).

    Args:
        namespace: If None, searches all namespaces
        limit:     Max events to return
    """
    core = get_core_v1()
    try:
        if namespace:
            event_list = core.list_namespaced_event(
                namespace=namespace,
                field_selector="type=Warning",
                limit=limit,
            )
        else:
            event_list = core.list_event_for_all_namespaces(
                field_selector="type=Warning",
                limit=limit,
            )
    except ApiException as e:
        logger.error(f"Failed to list warning events: {e}")
        raise

    return _sort_events([_fmt_event(ev) for ev in event_list.items])


def get_events_for_resource(
    name: str,
    kind: str = "Pod",
    namespace: str = "default",
) -> list[dict]:
    """
    Fetch events for any named Kubernetes resource.

    Args:
        name:      Resource name (e.g., "my-pod", "my-deployment")
        kind:      Resource kind (Pod, Deployment, Node, Service, etc.)
        namespace: Namespace to search

    Returns:
        List of events related to this resource
    """
    core = get_core_v1()
    selector = f"involvedObject.name={name},involvedObject.kind={kind}"
    try:
        if kind == "Node":
            event_list = core.list_event_for_all_namespaces(field_selector=selector)
        else:
            event_list = core.list_namespaced_event(
                namespace=namespace,
                field_selector=selector,
            )
    except ApiException as e:
        logger.error(f"Failed to fetch events for {kind}/{name}: {e}")
        raise

    return _sort_events([_fmt_event(ev) for ev in event_list.items])


def get_recent_warning_summary(namespace: Optional[str] = None, limit: int = 20) -> list[dict]:
    """
    Returns a compact summary of recent warnings — useful as context for the AI agent.

    Each entry includes: namespace, resource_kind, resource_name, reason, message, count.
    """
    warnings = list_warning_events(namespace=namespace, limit=limit)
    return [
        {
            "namespace":     ev["namespace"],
            "resource_kind": ev["involved_object"]["kind"],
            "resource_name": ev["involved_object"]["name"],
            "reason":        ev["reason"],
            "message":       ev["message"],
            "count":         ev["count"],
            "last_time":     ev["last_time"],
        }
        for ev in warnings
    ]


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _fmt_event(ev) -> dict:
    return {
        "name":       ev.metadata.name,
        "namespace":  ev.metadata.namespace,
        "type":       ev.type,            # Normal | Warning
        "reason":     ev.reason,
        "message":    ev.message,
        "count":      ev.count,
        "first_time": ev.first_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.first_timestamp else None,
        "last_time":  ev.last_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ") if ev.last_timestamp else None,
        "involved_object": {
            "kind":      ev.involved_object.kind,
            "name":      ev.involved_object.name,
            "namespace": ev.involved_object.namespace,
        },
        "source": {
            "component": ev.source.component if ev.source else None,
            "host":      ev.source.host if ev.source else None,
        },
    }


def _sort_events(events: list[dict]) -> list[dict]:
    """Sort: Warning first, then by last_time descending (most recent first)."""
    return sorted(
        events,
        key=lambda e: (e["type"] != "Warning", e["last_time"] or ""),
        reverse=False,
    )
