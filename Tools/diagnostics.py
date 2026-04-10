"""
tools/diagnostics.py

High-level diagnostic aggregator.

This module combines data from pods, events, metrics, and deployments
to produce a rich "diagnosis bundle" for a given target.

This is the primary data-gathering layer for the AI agent — it provides
everything the LLM needs to reason about a problem in a single call.

Functions:
  - diagnose_pod(name, namespace)              → full pod diagnosis bundle
  - diagnose_deployment(name, namespace)       → full deployment diagnosis bundle
  - diagnose_service(name, namespace)          → service health & connectivity
  - cluster_health_snapshot(namespace)         → high-level cluster overview
  - quick_summary(namespace)                   → minimal context for agent queries
"""

import logging
from typing import Optional

from .pods        import get_pod_status, get_pod_logs, get_pod_events, detect_pod_issues
from .deployments import get_deployment, get_deployment_events
from .services    import list_services, get_service
from .nodes       import list_nodes, detect_node_issues
from .events      import list_warning_events, get_recent_warning_summary
from .metrics     import get_pod_metrics, list_pod_metrics, detect_resource_pressure
from .namespaces  import list_namespaces

logger = logging.getLogger(__name__)


def diagnose_pod(name: str, namespace: str = "default") -> dict:
    """
    Produce a comprehensive diagnosis bundle for a pod.

    This is a single call that gathers ALL data the AI agent needs to:
    1. Identify what is wrong
    2. Understand why
    3. Suggest a fix

    SMART COLLECTION: Skips unnecessary API calls based on pod status
    - If Pending: Don't collect logs (pod hasn't started)
    - If Pending: Don't collect metrics (meaningless)
    - Only collect prev_logs if pod has CrashLoopBackOff/OOMKilled

    Returns:
        {
          "target":     {"kind": "Pod", "name": ..., "namespace": ...},
          "issues":     [...],         # detected issue types
          "severity":   "critical" | "warning" | "healthy",
          "status":     {...},         # pod status summary
          "events":     [...],         # recent pod events (warnings first)
          "logs":       "...",         # last 100 lines of current logs
          "prev_logs":  "...",         # logs from previous (crashed) instance
          "metrics":    {...},         # current CPU/memory usage
        }
    """
    result: dict = {
        "target":    {"kind": "Pod", "name": name, "namespace": namespace},
        "issues":    [],
        "severity":  "unknown",
        "status":    {},
        "events":    [],
        "logs":      "",
        "prev_logs": "",
        "metrics":   {},
    }

    # 1. Issue detection (ALWAYS run first — determines rest of collection)
    try:
        issue_data = detect_pod_issues(name, namespace)
        result["issues"]   = issue_data["issues"]
        result["severity"] = issue_data["severity"]
        result["status"]   = issue_data["details"]
    except Exception as e:
        logger.warning(f"Could not detect issues for pod {namespace}/{name}: {e}")
        result["severity"] = "unknown"
        return result  # Early exit if we can't determine status

    # 2. Events (skip if Pending — won't tell us much)
    if "Pending" not in result["issues"]:
        try:
            result["events"] = get_pod_events(name, namespace)
        except Exception as e:
            logger.warning(f"Could not fetch events for pod {namespace}/{name}: {e}")

    # 3. Current logs (SKIP if Pending — pod hasn't started running)
    if "Pending" not in result["issues"]:
        try:
            result["logs"] = get_pod_logs(name, namespace, tail_lines=100)
        except Exception as e:
            logger.warning(f"Could not fetch logs for pod {namespace}/{name}: {e}")

    # 4. Previous logs (ONLY if crashed - saves API call for healthy pods)
    if any(issue in result["issues"] for issue in ["CrashLoopBackOff", "OOMKilled", "HighRestartCount"]):
        try:
            result["prev_logs"] = get_pod_logs(name, namespace, previous=True, tail_lines=100)
        except Exception:
            result["prev_logs"] = "[No previous logs available]"

    # 5. Metrics (SKIP if Pending — pod not running yet)
    if "Pending" not in result["issues"]:
        try:
            result["metrics"] = get_pod_metrics(name, namespace)
        except Exception as e:
            logger.warning(f"Could not fetch metrics for pod {namespace}/{name}: {e}")
            result["metrics"] = {"error": "Metrics Server unavailable"}

    return result


def diagnose_deployment(name: str, namespace: str = "default", include_pod_details: bool = False, include_resource_pressure: bool = False) -> dict:
    """
    Produce a diagnosis bundle for a Deployment and its pods.

    Args:
        name:                      Deployment name
        namespace:                 Target namespace
        include_pod_details:       If True, run full diagnose_pod() on each related pod (slower, more thorough)
                                   If False (default), only return lightweight pod status (fast, ~1-2 API calls total)
        include_resource_pressure: If True, run detect_resource_pressure() for the namespace (expensive — ~N API calls)
                                   If False (default), skip this analysis (fast, good for large namespaces)

    Returns:
        {
          "target":      {"kind": "Deployment", ...},
          "deployment":  {...},   # deployment summary
          "events":      [...],   # deployment events
          "pod_statuses": [...],  # lightweight pod status (always included)
          "pod_diagnoses": [...], # only if include_pod_details=True (expensive!)
          "resource_pressure": {...},  # only if include_resource_pressure=True (expensive!)
        }
    """
    result: dict = {
        "target":            {"kind": "Deployment", "name": name, "namespace": namespace},
        "deployment":        {},
        "events":            [],
        "pod_statuses":      [],
        "pod_diagnoses":     [],
        "resource_pressure": {},
    }

    # 1. Deployment summary
    try:
        result["deployment"] = get_deployment(name, namespace)
    except Exception as e:
        logger.warning(f"Could not get deployment {namespace}/{name}: {e}")
        return {
            **result,
            "error": f"Failed to get deployment: {e}",
        }

    # 2. Deployment-level events
    try:
        result["events"] = get_deployment_events(name, namespace)
    except Exception as e:
        logger.warning(f"Could not get events for deployment {namespace}/{name}: {e}")

    # 3. Find related pods (lightweight list, not detailed diagnosis)
    try:
        from .pods import list_pods
        all_pods = list_pods(namespace)
        selector = result["deployment"].get("selector", {})

        if not selector:
            logger.warning(f"Deployment {namespace}/{name} has no selector label")
            result["pod_statuses"] = []
        else:
            related_pods = [
                p for p in all_pods
                if _labels_match(p.get("labels", {}), selector)
            ]
            
            # Always return lightweight pod status
            result["pod_statuses"] = related_pods

            # Optionally run expensive per-pod diagnosis (4-5 API calls per pod)
            if include_pod_details:
                for pod in related_pods:
                    try:
                        diag = diagnose_pod(pod["name"], namespace)
                        result["pod_diagnoses"].append(diag)
                    except Exception as e:
                        logger.warning(f"Could not diagnose pod {pod['name']}: {e}")

    except Exception as e:
        logger.warning(f"Could not list pods for deployment {namespace}/{name}: {e}")

    # 4. Resource pressure analysis (ONLY if explicitly requested — expensive!)
    if include_resource_pressure:
        try:
            result["resource_pressure"] = detect_resource_pressure(namespace)
        except Exception as e:
            logger.warning(f"Resource pressure analysis failed: {e}")

    return result


def cluster_health_snapshot(namespace: Optional[str] = None) -> dict:
    """
    Produce a high-level cluster health overview.

    Used for the dashboard "cluster overview" panel and as AI agent context
    for general queries ("what's wrong in the cluster?").

    Returns:
        {
          "namespaces":        [...],
          "node_health":       [...],
          "recent_warnings":   [...],
          "resource_pressure": {...},
          "summary": {
            "total_nodes":    int,
            "unhealthy_nodes": int,
            "warning_count":  int,
          }
        }
    """
    snapshot: dict = {
        "namespaces":        [],
        "node_health":       [],
        "recent_warnings":   [],
        "resource_pressure": {},
        "summary":           {},
    }

    # Namespaces
    try:
        snapshot["namespaces"] = list_namespaces()
    except Exception as e:
        logger.warning(f"Could not list namespaces: {e}")

    # Node health
    node_health = []
    unhealthy   = 0
    try:
        nodes = list_nodes()
        for node in nodes:
            try:
                node_diag = detect_node_issues(node["name"])
                node_health.append({
                    "name":     node["name"],
                    "issues":   node_diag["issues"],
                    "severity": node_diag["severity"],
                })
                if node_diag["severity"] in ("critical", "warning"):
                    unhealthy += 1
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not assess node health: {e}")
    snapshot["node_health"] = node_health

    # Recent warnings
    try:
        snapshot["recent_warnings"] = get_recent_warning_summary(namespace=namespace, limit=30)
    except Exception as e:
        logger.warning(f"Could not fetch recent warnings: {e}")

    # Resource pressure
    try:
        if namespace:
            snapshot["resource_pressure"] = detect_resource_pressure(namespace)
    except Exception as e:
        logger.warning(f"Resource pressure analysis failed: {e}")

    # Summary
    snapshot["summary"] = {
        "total_nodes":    len(node_health),
        "unhealthy_nodes": unhealthy,
        "warning_count":  len(snapshot["recent_warnings"]),
    }

    return snapshot


def diagnose_service(name: str, namespace: str = "default") -> dict:
    """
    Produce a diagnostic bundle for a Service and its endpoints.

    Useful for troubleshooting "service unreachable" or "no endpoints" issues.

    Returns:
        {
          "target":       {"kind": "Service", "name": ..., "namespace": ...},
          "service":      {...},              # Service summary (ClusterIP, ports, selector)
          "endpoints":    {...},              # Endpoint status (ready/not-ready addresses)
          "backend_pods": [...],              # Pods matching the selector
          "issues":       [...],              # detected problems (NoEndpoints, SelectorMismatch, etc.)
          "severity":     "critical" | "warning" | "healthy",
        }
    """
    result: dict = {
        "target":       {"kind": "Service", "name": name, "namespace": namespace},
        "service":      {},
        "endpoints":    {},
        "backend_pods": [],
        "issues":       [],
        "severity":     "unknown",
    }

    # 1. Service details
    try:
        result["service"] = get_service(name, namespace)
    except Exception as e:
        logger.warning(f"Could not get service {namespace}/{name}: {e}")
        result["issues"].append("ServiceNotFound")
        result["severity"] = "critical"
        return result

    # 2. Service endpoints (direct Endpoints API — no external dependency)
    try:
        from .client import get_core_v1
        core = get_core_v1()
        ep_obj = core.read_namespaced_endpoints(name, namespace)
        subsets = ep_obj.subsets or []
        ready_count = 0
        not_ready_count = 0
        for subset in subsets:
            ready_count += len(subset.addresses or [])
            not_ready_count += len(subset.not_ready_addresses or [])
        result["endpoints"] = {
            "ready_count":     ready_count,
            "not_ready_count": not_ready_count,
        }
        if ready_count == 0:
            result["issues"].append("NoReadyEndpoints")
    except Exception as e:
        logger.warning(f"Could not get endpoints for service {namespace}/{name}: {e}")
        result["issues"].append("EndpointsUnavailable")

    # 3. Backend pods
    try:
        from .pods import list_pods
        selector = result["service"].get("selector", {})
        all_pods = list_pods(namespace)
        result["backend_pods"] = [
            p for p in all_pods
            if _labels_match(p.get("labels", {}), selector)
        ]
        if not result["backend_pods"] and selector:
            result["issues"].append("SelectorMatchesNoPods")
    except Exception as e:
        logger.warning(f"Could not list pods for service {namespace}/{name}: {e}")

    # Severity assessment
    if "NoReadyEndpoints" in result["issues"] or "ServiceNotFound" in result["issues"]:
        result["severity"] = "critical"
    elif result["issues"]:
        result["severity"] = "warning"
    else:
        result["severity"] = "healthy"

    return result


def quick_summary(namespace: str = "default") -> dict:
    """
    Return a minimal, fast context summary for the AI agent.

    Used to answer quick queries like "what's the health status?" without
    expensive per-resource diagnostics.

    Returns:
        {
          "namespace":       str,
          "resources": {
            "pods":       <count>,
            "deployments": <count>,
            "services":    <count>,
            "nodes":       <count>,
          },
          "issues":          [...],  # recent warnings/errors
          "pressure":        {...},  # resource pressure summary
        }
    """
    summary: dict = {
        "namespace":  namespace,
        "resources": {
            "pods":        0,
            "deployments": 0,
            "services":    0,
            "nodes":       0,
        },
        "issues":   [],
        "pressure": {},
    }

    # Count resources
    try:
        from .pods import list_pods as _list_pods
        summary["resources"]["pods"] = len(_list_pods(namespace))
    except Exception as e:
        logger.debug(f"Could not count pods: {e}")

    try:
        from .deployments import list_deployments as _list_deps
        summary["resources"]["deployments"] = len(_list_deps(namespace))
    except Exception as e:
        logger.debug(f"Could not count deployments: {e}")

    try:
        summary["resources"]["services"] = len(list_services(namespace))
    except Exception as e:
        logger.debug(f"Could not count services: {e}")

    try:
        summary["resources"]["nodes"] = len(list_nodes())
    except Exception as e:
        logger.debug(f"Could not count nodes: {e}")

    # Recent issues
    try:
        summary["issues"] = get_recent_warning_summary(namespace=namespace, limit=5)
    except Exception as e:
        logger.debug(f"Could not fetch recent issues: {e}")

    # Resource pressure
    try:
        summary["pressure"] = detect_resource_pressure(namespace)
    except Exception as e:
        logger.debug(f"Could not assess resource pressure: {e}")

    return summary


# ─────────────────────────────────────────────
# IMPORTS FIX
# ─────────────────────────────────────────────

def _safe_call(func, default, context: str):
    """Helper to safely call a function with logging."""
    try:
        return func()
    except Exception as e:
        logger.debug(f"Safe call failed ({context}): {e}")
        return default


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _labels_match(pod_labels: dict, selector: dict) -> bool:
    """Check if pod_labels contains all key-value pairs in selector."""
    if not selector:
        return False
    return all(pod_labels.get(k) == v for k, v in selector.items())