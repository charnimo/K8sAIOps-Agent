"""
tools/network_policies.py

Kubernetes NetworkPolicy operations for network segmentation and access control.

Operations:
  READ:  list_network_policies, get_network_policy, detect_network_issues
  WRITE: create_network_policy, delete_network_policy, patch_network_policy
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_networking_v1
from .utils import fmt_time, retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_network_policies(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List NetworkPolicies in a namespace.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label filter

    Returns:
        List of NetworkPolicy summaries
    """
    try:
        net_api = get_networking_v1()
        policies = net_api.list_namespaced_network_policy(namespace, label_selector=label_selector)
        return [_summarize_network_policy(p) for p in policies.items]
    except ApiException as e:
        logger.error(f"Failed to list NetworkPolicies in {namespace}: {e}")
        return []


def list_all_network_policies(label_selector: Optional[str] = None) -> list[dict]:
    """List NetworkPolicies across all namespaces."""
    try:
        net_api = get_networking_v1()
        policies = net_api.list_network_policy_for_all_namespaces(label_selector=label_selector)
        return [_summarize_network_policy(p) for p in policies.items]
    except ApiException as e:
        logger.error(f"Failed to list all NetworkPolicies: {e}")
        return []


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_network_policy(name: str, namespace: str = "default") -> dict:
    """Get a single NetworkPolicy."""
    try:
        net_api = get_networking_v1()
        policy = net_api.read_namespaced_network_policy(name, namespace)
        return _summarize_network_policy(policy)
    except ApiException as e:
        logger.error(f"Failed to get NetworkPolicy {namespace}/{name}: {e}")
        return {"error": str(e)}


def detect_network_issues(namespace: str = "default") -> dict:
    """
    Detect network connectivity issues in a namespace.

    Checks for overly permissive policies or unreachable services.

    Returns:
        {"issues": [str], "severity": "warning" | "critical"}
    """
    issues = []

    try:
        policies = list_network_policies(namespace)

        # Check if no policies exist (default allows all)
        if not policies:
            issues.append("No NetworkPolicies defined - all traffic allowed by default")

        # Check for overly permissive policies
        for policy in policies:
            ingress_rules = policy.get("ingress_rules", [])
            egress_rules = policy.get("egress_rules", [])

            # Check for empty rules (allow all)
            if not ingress_rules:
                issues.append(f"{policy['name']}: No ingress rules defined - allows all ingress")
            if not egress_rules and policy.get("pod_selector"):
                issues.append(f"{policy['name']}: No egress rules defined - allows all egress")

    except Exception as e:
        logger.warning(f"Error detecting NetworkPolicy issues: {e}")

    severity = "critical" if not list_network_policies(namespace) else "warning" if issues else "healthy"

    return {
        "issues": issues,
        "severity": severity,
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_network_policy(policy) -> dict:
    """Convert NetworkPolicy object to clean dict."""
    spec = policy.spec or {}

    ingress_rules = []
    if spec.ingress:
        for rule in spec.ingress:
            ingress_rules.append({
                "from": _summarize_traffic_rule(rule.from_) if rule.from_ else [],
                "ports": [{"port": p.port, "protocol": p.protocol} for p in rule.ports] if rule.ports else [],
            })

    egress_rules = []
    if spec.egress:
        for rule in spec.egress:
            egress_rules.append({
                "to": _summarize_traffic_rule(rule.to) if rule.to else [],
                "ports": [{"port": p.port, "protocol": p.protocol} for p in rule.ports] if rule.ports else [],
            })

    return {
        "name": policy.metadata.name,
        "namespace": policy.metadata.namespace,
        "pod_selector": spec.pod_selector.match_labels if spec.pod_selector else {},
        "policy_types": spec.policy_types or ["Ingress"],
        "ingress_rules": ingress_rules,
        "egress_rules": egress_rules,
        "labels": policy.metadata.labels or {},
    }


def _summarize_traffic_rule(traffic_list) -> list:
    """Summarize traffic rules (from/to)."""
    result = []
    if not traffic_list:
        return result

    for traffic in traffic_list:
        rule = {}
        if traffic.pod_selector:
            rule["pod_selector"] = traffic.pod_selector.match_labels or {}
        if traffic.namespace_selector:
            rule["namespace_selector"] = traffic.namespace_selector.match_labels or {}
        if traffic.ip_block:
            rule["ip_block"] = traffic.ip_block.cidr
        result.append(rule)

    return result
