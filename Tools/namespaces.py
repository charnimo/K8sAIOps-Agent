"""
Namespace read utilities.

READ:
  - list_namespaces()            -> namespace summaries
  - get_namespace(name)          -> single namespace details
  - get_namespace_events(name)   -> namespace-scoped events
"""

from datetime import datetime, timezone
import logging

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1

logger = logging.getLogger(__name__)



def list_namespaces() -> list[dict]:
    """List all namespaces with lifecycle and age information."""
    core = get_core_v1()
    try:
        ns_list = core.list_namespace()
    except ApiException as e:
        logger.error(f"Failed to list namespaces: {e}")
        raise

    return [_summarize_namespace(ns) for ns in ns_list.items]



def get_namespace(name: str) -> dict:
    """Get details for a single namespace."""
    core = get_core_v1()
    try:
        ns = core.read_namespace(name=name)
    except ApiException as e:
        logger.error(f"Namespace {name} not found: {e}")
        raise

    return _summarize_namespace(ns)



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



def _summarize_namespace(ns) -> dict:
    creation = ns.metadata.creation_timestamp
    age = None
    if creation:
        secs = int((datetime.now(timezone.utc) - creation).total_seconds())
        if secs < 3600:
            age = f"{max(secs // 60, 0)}m"
        elif secs < 86400:
            age = f"{secs // 3600}h"
        else:
            age = f"{secs // 86400}d"

    return {
        "name": ns.metadata.name,
        "phase": ns.status.phase if ns.status else None,
        "age": age,
        "labels": ns.metadata.labels or {},
        "annotations": ns.metadata.annotations or {},
    }
