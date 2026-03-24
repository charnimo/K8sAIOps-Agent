"""
k8s_client/diagnostics.py

High-level diagnostic aggregator.

This module combines data from pods, events, metrics, and deployments
to produce a rich "diagnosis bundle" for a given target.

This is the primary data-gathering layer for the AI agent — it provides
everything the LLM needs to reason about a problem in a single call.

Functions:
  - diagnose_pod(name, namespace)              → full pod diagnosis bundle
  - diagnose_deployment(name, namespace)       → full deployment diagnosis bundle
  - cluster_health_snapshot(namespace)         → high-level cluster overview
"""

import logging
from typing import Optional

from .pods        import get_pod_status, get_pod_logs, get_pod_events, detect_pod_issues
from .deployments import get_deployment, get_deployment_events
from .nodes       import list_nodes, detect_node_issues
from .events      import list_warning_events, get_recent_warning_summary
from .metrics     import get_pod_metrics, list_pod_metrics, list_node_metrics, detect_resource_pressure
from .namespaces  import list_namespaces

logger = logging.getLogger(__name__)


def diagnose_pod(name: str, namespace: str = "default") -> dict:
    """
    Produce a comprehensive diagnosis bundle for a pod.

    This is a single call that gathers ALL data the AI agent needs to:
    1. Identify what is wrong
    2. Understand why
    3. Suggest a fix

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

    # 1. Issue detection
    try:
        issue_data = detect_pod_issues(name, namespace)
        result["issues"]   = issue_data["issues"]
        result["severity"] = issue_data["severity"]
        result["status"]   = issue_data["details"]
    except Exception as e:
        logger.warning(f"Could not detect issues for pod {namespace}/{name}: {e}")
        result["severity"] = "unknown"

    # 2. Events
    try:
        result["events"] = get_pod_events(name, namespace)
    except Exception as e:
        logger.warning(f"Could not fetch events for pod {namespace}/{name}: {e}")

    # 3. Current logs
    try:
        result["logs"] = get_pod_logs(name, namespace, tail_lines=100)
    except Exception as e:
        logger.warning(f"Could not fetch logs for pod {namespace}/{name}: {e}")

    # 4. Previous logs (useful for CrashLoopBackOff)
    if any(issue in result["issues"] for issue in ["CrashLoopBackOff", "OOMKilled", "HighRestartCount"]):
        try:
            result["prev_logs"] = get_pod_logs(name, namespace, previous=True, tail_lines=100)
        except Exception:
            result["prev_logs"] = "[No previous logs available]"

    # 5. Metrics
    try:
        result["metrics"] = get_pod_metrics(name, namespace)
    except Exception as e:
        logger.warning(f"Could not fetch metrics for pod {namespace}/{name}: {e}")
        result["metrics"] = {"error": "Metrics Server unavailable"}

    return result


def diagnose_deployment(name: str, namespace: str = "default") -> dict:
    """
    Produce a diagnosis bundle for a Deployment and all its pods.

    Returns:
        {
          "target":      {"kind": "Deployment", ...},
          "deployment":  {...},   # deployment summary
          "events":      [...],   # deployment events
          "pod_diagnoses": [...], # diagnose_pod() result for each pod
          "resource_pressure": {...},  # memory/cpu pressure analysis
        }
    """
    result: dict = {
        "target":            {"kind": "Deployment", "name": name, "namespace": namespace},
        "deployment":        {},
        "events":            [],
        "pod_diagnoses":     [],
        "resource_pressure": {},
    }

    # 1. Deployment summary
    try:
        result["deployment"] = get_deployment(name, namespace)
    except Exception as e:
        logger.warning(f"Could not get deployment {namespace}/{name}: {e}")

    # 2. Deployment-level events
    try:
        result["events"] = get_deployment_events(name, namespace)
    except Exception as e:
        logger.warning(f"Could not get events for deployment {namespace}/{name}: {e}")

    # 3. Find and diagnose all related pods
    try:
        from .pods import list_pods
        all_pods = list_pods(namespace)
        selector = result["deployment"].get("selector", {})

        related_pods = [
            p for p in all_pods
            if _labels_match(p.get("labels", {}), selector)
        ]

        for pod in related_pods:
            try:
                diag = diagnose_pod(pod["name"], namespace)
                result["pod_diagnoses"].append(diag)
            except Exception as e:
                logger.warning(f"Could not diagnose pod {pod['name']}: {e}")

    except Exception as e:
        logger.warning(f"Could not list pods for deployment {namespace}/{name}: {e}")

    # 4. Resource pressure analysis
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


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _labels_match(pod_labels: dict, selector: dict) -> bool:
    """Check if pod_labels contains all key-value pairs in selector."""
    if not selector:
        return False
    return all(pod_labels.get(k) == v for k, v in selector.items())
