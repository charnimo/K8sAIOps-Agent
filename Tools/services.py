"""
k8s_tools/services.py

Service read operations (read-only for MVP).

READ:
  - list_services(namespace)      → all services in a namespace
  - get_service(name, namespace)  → single service detail
"""

import logging
from datetime import datetime, timezone
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1
from .utils import fmt_duration

logger = logging.getLogger(__name__)


def list_services(namespace: str = "default") -> list[dict]:
    """
    List all services in a namespace with status and endpoint info.

    Returns:
        List of service dicts with name, type, cluster_ip, endpoints, age.
    """
    core = get_core_v1()
    try:
        svc_list = core.list_namespaced_service(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list services in {namespace}: {e}")
        raise

    return [_summarize_service(svc) for svc in svc_list.items]


def list_all_services() -> list[dict]:
    """List services across ALL namespaces."""
    core = get_core_v1()
    try:
        svc_list = core.list_service_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all services: {e}")
        raise
    return [_summarize_service(svc) for svc in svc_list.items]


def get_service(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single service."""
    core = get_core_v1()
    try:
        svc = core.read_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Service {namespace}/{name} not found: {e}")
        raise
    return _summarize_service(svc)


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
