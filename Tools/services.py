"""
tools/services.py

Service read and action operations.

READ:
  - list_services(namespace)      → all services in a namespace
  - get_service(name, namespace)  → single service detail

ACTIONS (require user approval):
  - create_service(name, namespace, ...)       → create a new service
  - patch_service(name, namespace, spec)       → update service spec fields
  - delete_service(name, namespace)            → delete a service
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1
from .utils import fmt_duration, retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_services(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List services in a namespace with status and endpoint info.

    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector

    Returns:
        List of service dicts with name, type, cluster_ip, endpoints, age.
    """
    # Input validation
    namespace = validate_namespace(namespace)
    if label_selector:
        label_selector = sanitize_input(label_selector, "label_selector")
    
    core = get_core_v1()
    try:
        svc_list = core.list_namespaced_service(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list services in {namespace}: {e}")
        raise

    return [_summarize_service(svc) for svc in svc_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
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


@retry_on_transient(max_attempts=3, backoff_base=1.0)
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
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def create_service(
    name: str,
    namespace: str = "default",
    service_type: str = "ClusterIP",
    selector: Optional[dict] = None,
    ports: Optional[list[dict]] = None,
    labels: Optional[dict] = None,
) -> dict:
    """
    Create a new Kubernetes Service.

    ⚠️  ACTION — requires user approval.

    Args:
        name:           Service name
        namespace:      Namespace
        service_type:   "ClusterIP" (default), "NodePort", "LoadBalancer", "ExternalName"
        selector:       Dict of pod labels to target (e.g., {"app": "web"})
        ports:          List of port dicts: [{"port": 80, "target_port": 8080, "protocol": "TCP", "name": "http"}]
        labels:         Dict of labels for the service itself

    Returns:
        {"success": bool, "message": str, "service_name": str}
    """
    from kubernetes import client
    
    if not ports:
        ports = [{"port": 80, "target_port": 8080, "protocol": "TCP"}]

    # Convert port list to V1ServicePort objects
    port_objs = []
    for p in ports:
        port_objs.append(
            client.V1ServicePort(
                port=p.get("port"),
                target_port=p.get("target_port"),
                protocol=p.get("protocol", "TCP"),
                name=p.get("name"),
            )
        )

    service_body = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels or {}),
        spec=client.V1ServiceSpec(
            type=service_type,
            selector=selector or {},
            ports=port_objs,
        ),
    )

    core = get_core_v1()
    try:
        core.create_namespaced_service(namespace=namespace, body=service_body)
        logger.info(f"[ACTION] Created service {namespace}/{name} (type={service_type})")
        return {
            "success":       True,
            "message":       f"Service '{name}' created in namespace '{namespace}'.",
            "service_name":  name,
        }
    except ApiException as e:
        logger.error(f"Failed to create service {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def patch_service(
    name: str,
    namespace: str = "default",
    selector: Optional[dict] = None,
    labels: Optional[dict] = None,
    ports: Optional[list[dict]] = None,
) -> dict:
    """
    Update a Service's selector, labels, or ports.

    ⚠️  ACTION — requires user approval.

    Args:
        name:       Service name
        namespace:  Namespace
        selector:   New pod selector (replaces current)
        labels:     New service labels (replaces current)
        ports:      New port spec (replaces current)

    Returns:
        {"success": bool, "message": str}
    """
    from kubernetes import client
    
    patch_body = {}

    if labels is not None:
        patch_body["metadata"] = {"labels": labels}

    if selector is not None:
        patch_body["spec"] = {"selector": selector}

    if ports is not None:
        port_objs = []
        for p in ports:
            port_objs.append(
                client.V1ServicePort(
                    port=p.get("port"),
                    target_port=p.get("target_port"),
                    protocol=p.get("protocol", "TCP"),
                    name=p.get("name"),
                )
            )
        if "spec" not in patch_body:
            patch_body["spec"] = {}
        patch_body["spec"]["ports"] = port_objs

    if not patch_body:
        return {"success": False, "message": "No patch data provided (selector, labels, or ports)."}

    core = get_core_v1()
    try:
        core.patch_namespaced_service(name=name, namespace=namespace, body=patch_body)
        logger.info(f"[ACTION] Patched service {namespace}/{name}")
        return {
            "success": True,
            "message": f"Service '{name}' in namespace '{namespace}' updated.",
        }
    except ApiException as e:
        logger.error(f"Failed to patch service {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def delete_service(name: str, namespace: str = "default") -> dict:
    """
    Delete a Service.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Service name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation + defensive check
    try:
        name = validate_name(name)
        namespace = validate_namespace(namespace)
    except ValueError as e:
        return {"success": False, "message": f"Invalid input: {str(e)}"}
    
    core = get_core_v1()
    
    # Defensive check: verify service exists before deleting
    try:
        core.read_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {"success": False, "message": f"Service {namespace}/{name} not found"}
        raise
    
    try:
        core.delete_namespaced_service(name=name, namespace=namespace)
        logger.info(f"[ACTION] Deleted service {namespace}/{name}")
        return {
            "success": True,
            "message": f"Service '{name}' deleted from namespace '{namespace}'.",
        }
    except ApiException as e:
        logger.error(f"Failed to delete service {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


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
        "external_ips":   svc.spec.external_i_ps or [],
        "ports":          ports,
        "selector":       svc.spec.selector or {},
        "endpoints":      endpoints,
        "age":            age,
        "labels":         svc.metadata.labels or {},
    }
