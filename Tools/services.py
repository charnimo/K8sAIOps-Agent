"""
Tools/services.py

Service read operations (read-only for MVP).

READ:
  - list_services(namespace)      → all services in a namespace
  - get_service(name, namespace)  → single service detail
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1
from .utils import fmt_duration

logger = logging.getLogger(__name__)


def list_services(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List services in a namespace with status and endpoint info.

    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector

    Returns:
        List of service dicts with name, type, cluster_ip, endpoints, age.
    """
    core = get_core_v1()
    try:
        svc_list = core.list_namespaced_service(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list services in {namespace}: {e}")
        raise

    return [_summarize_service(svc) for svc in svc_list.items]


def list_all_services(label_selector: Optional[str] = None) -> list[dict]:
    """List services across ALL namespaces.
    
    Args:
        label_selector: Optional Kubernetes label selector
    """
    core = get_core_v1()
    try:
        svc_list = core.list_service_for_all_namespaces(label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list all services: {e}")
        raise
    return [_summarize_service(svc) for svc in svc_list.items]


def get_service(name: str, namespace: str = "default") -> dict:
    """
    Fetch a detailed summary for a single service.
    Includes has_selector and matching_pods count for networking diagnostics.
    """
    core = get_core_v1()
    try:
        svc = core.read_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Service {namespace}/{name} not found: {e}")
        raise

    summary = _summarize_service(svc)
    selector = svc.spec.selector or {}
    summary["has_selector"] = bool(selector)

    matching_pods = 0
    if selector:
        label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
        try:
            pod_list = core.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
            matching_pods = len(pod_list.items)
        except ApiException:
            pass
    summary["matching_pods"] = matching_pods
    return summary


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_service(svc) -> dict:
    """Convert a raw Service object into a clean summary dict."""
    creation = svc.metadata.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    # Port info
    ports = []
    if svc.spec.ports:
        for port in svc.spec.ports:
            ports.append({
                "name":       port.name,
                "protocol":   port.protocol,
                "port":       port.port,
                "target_port": port.target_port,
                "node_port":  port.node_port,
            })

    # Endpoints
    endpoints = []
    if svc.status and svc.status.load_balancer:
        if svc.status.load_balancer.ingress:
            endpoints = [
                {"ip": ing.ip, "hostname": ing.hostname}
                for ing in svc.status.load_balancer.ingress
            ]

    return {
        "name":           svc.metadata.name,
        "namespace":      svc.metadata.namespace,
        "type":           svc.spec.type,  # ClusterIP, NodePort, LoadBalancer, ExternalName
        "cluster_ip":     svc.spec.cluster_ip,
        "external_ips":   svc.spec.external_ips or [],
        "ports":          ports,
        "selector":       svc.spec.selector or {},
        "endpoints":      endpoints,
        "age":            age,
        "labels":         svc.metadata.labels or {},
    }
