"""
tools/resource_quotas.py

Kubernetes ResourceQuota and LimitRange operations for resource management and scheduling diagnosis.

Operations:
  READ: list_resource_quotas, get_resource_quota, list_limit_ranges, get_limit_range, detect_quota_pressure
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1
from .utils import fmt_time, retry_on_transient, validate_namespace, parse_cpu_m, parse_memory_mi

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_resource_quotas(namespace: str = "default") -> list[dict]:
    """
    List ResourceQuotas in a namespace.

    Shows CPU, memory, pod count limits and current usage.

    Args:
        namespace: Kubernetes namespace

    Returns:
        List of ResourceQuota summaries with current usage vs limits
    """
    core = get_core_v1()
    try:
        quotas = core.list_namespaced_resource_quota(namespace=namespace)
        return [_summarize_resource_quota(q) for q in quotas.items]
    except ApiException as e:
        logger.error(f"Failed to list ResourceQuotas in {namespace}: {e}")
        return []


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_resource_quota(name: str, namespace: str = "default") -> dict:
    """Get a single ResourceQuota with current usage."""
    core = get_core_v1()
    try:
        quota = core.read_namespaced_resource_quota(name=name, namespace=namespace)
        return _summarize_resource_quota(quota)
    except ApiException as e:
        logger.error(f"Failed to get ResourceQuota {namespace}/{name}: {e}")
        return {"error": str(e)}


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_limit_ranges(namespace: str = "default") -> list[dict]:
    """
    List LimitRanges in a namespace.

    Shows default/minimum/maximum CPU and memory restrictions per Pod/Container.

    Args:
        namespace: Kubernetes namespace

    Returns:
        List of LimitRange summaries
    """
    core = get_core_v1()
    try:
        limits = core.list_namespaced_limit_range(namespace=namespace)
        return [_summarize_limit_range(lr) for lr in limits.items]
    except ApiException as e:
        logger.error(f"Failed to list LimitRanges in {namespace}: {e}")
        return []


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_limit_range(name: str, namespace: str = "default") -> dict:
    """Get a single LimitRange."""
    core = get_core_v1()
    try:
        limit = core.read_namespaced_limit_range(name=name, namespace=namespace)
        return _summarize_limit_range(limit)
    except ApiException as e:
        logger.error(f"Failed to get LimitRange {namespace}/{name}: {e}")
        return {"error": str(e)}


def detect_quota_pressure(namespace: str = "default") -> dict:
    """
    Detect if a namespace is under ResourceQuota pressure.

    Returns high-level warning if quotas are nearly exhausted.

    Returns:
        {
          "namespace": "default",
          "under_pressure": bool,
          "pressures": ["pods exhausted", "CPU exhausted", ...],
          "quotas": [ResourceQuota summaries]
        }
    """
    quotas = list_resource_quotas(namespace)

    pressures = []
    for quota in quotas:
        used = quota.get("used", {})
        limits = quota.get("hard", {})

        for resource, limit_str in limits.items():
            if resource.startswith("pods"):
                try:
                    used_count = int(used.get("pods", 0) or 0)
                    limit_count = int(limit_str or 0)
                    if limit_count > 0 and used_count >= limit_count * 0.8:
                        pressures.append(f"Pods quota {used_count}/{limit_count} ({int(100 * used_count / limit_count)}%)")
                except (ValueError, TypeError):
                    pass

            elif resource == "requests.cpu":
                try:
                    used_cpu = parse_cpu_m(str(used.get("requests.cpu", "0")))
                    limit_cpu = parse_cpu_m(str(limit_str))
                    if limit_cpu > 0 and used_cpu >= limit_cpu * 0.8:
                        pressures.append(f"CPU quota {int(used_cpu)}m/{int(limit_cpu)}m ({int(100 * used_cpu / limit_cpu)}%)")
                except (ValueError, TypeError):
                    pass

            elif resource == "requests.memory":
                try:
                    used_mem = parse_memory_mi(str(used.get("requests.memory", "0")))
                    limit_mem = parse_memory_mi(str(limit_str))
                    if limit_mem > 0 and used_mem >= limit_mem * 0.8:
                        pressures.append(f"Memory quota {int(used_mem)}Mi/{int(limit_mem)}Mi ({int(100 * used_mem / limit_mem)}%)")
                except (ValueError, TypeError):
                    pass

    return {
        "namespace": namespace,
        "under_pressure": len(pressures) > 0,
        "pressures": pressures,
        "quotas": quotas,
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_resource_quota(quota) -> dict:
    """Convert ResourceQuota object to clean dict."""
    spec = quota.spec or {}
    status = quota.status or {}

    return {
        "name": quota.metadata.name,
        "namespace": quota.metadata.namespace,
        "hard": dict(spec.hard or {}),
        "used": dict(status.used or {}),
        "scopes": spec.scopes or [],
        "labels": quota.metadata.labels or {},
    }


def _summarize_limit_range(limit_range) -> dict:
    """Convert LimitRange object to clean dict."""
    spec = limit_range.spec or {}

    limits = []
    for limit in spec.limits or []:
        limit_dict = {
            "type": limit.type,
            "default": dict(limit.default or {}),
            "default_request": dict(limit.default_request or {}),
            "min": dict(limit.min or {}),
            "max": dict(limit.max or {}),
            "max_limit_request_ratio": dict(limit.max_limit_request_ratio or {}),
        }
        limits.append(limit_dict)

    return {
        "name": limit_range.metadata.name,
        "namespace": limit_range.metadata.namespace,
        "limits": limits,
        "labels": limit_range.metadata.labels or {},
    }
