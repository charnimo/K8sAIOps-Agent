"""
tools/ingress.py

Kubernetes Ingress resource operations (HTTP(S) routing rules).

Operations:
  READ:  list_ingresses, get_ingress, detect_ingress_issues
  WRITE: create_ingress, delete_ingress, patch_ingress
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .utils import fmt_time

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_ingresses(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List Ingress objects in a namespace.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label filter

    Returns:
        List of Ingress summaries with hosts, backends, TLS info
    """
    try:
        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        ingresses = net_api.list_namespaced_ingress(namespace, label_selector=label_selector)
        return [_summarize_ingress(ing) for ing in ingresses.items]
    except ApiException as e:
        logger.error(f"Failed to list Ingresses in {namespace}: {e}")
        return []


def list_all_ingresses(label_selector: Optional[str] = None) -> list[dict]:
    """List Ingresses across all namespaces."""
    try:
        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        ingresses = net_api.list_ingress_for_all_namespaces(label_selector=label_selector)
        return [_summarize_ingress(ing) for ing in ingresses.items]
    except ApiException as e:
        logger.error(f"Failed to list all Ingresses: {e}")
        return []


def get_ingress(name: str, namespace: str = "default") -> dict:
    """Get a single Ingress object."""
    try:
        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        ingress = net_api.read_namespaced_ingress(name, namespace)
        return _summarize_ingress(ingress)
    except ApiException as e:
        logger.error(f"Failed to get Ingress {namespace}/{name}: {e}")
        return {"error": str(e)}


def detect_ingress_issues(name: str, namespace: str = "default") -> dict:
    """
    Detect issues with an Ingress (missing backends, no IP, TLS problems, etc.).

    Returns:
        {"issues": [str], "severity": "healthy" | "warning" | "critical"}
    """
    try:
        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        ingress = net_api.read_namespaced_ingress(name, namespace)
    except ApiException as e:
        return {"issues": [f"Ingress not found: {e}"], "severity": "critical"}

    issues = []
    status = ingress.status or {}

    # Check for ingress IP/hostname
    if not status.load_balancer or not status.load_balancer.ingress:
        issues.append("Ingress has no LoadBalancer IP/hostname assigned")

    # Check rules exist
    if not ingress.spec or not ingress.spec.rules:
        issues.append("Ingress has no routing rules defined")

    # Check for TLS secrets if TLS is configured
    if ingress.spec and ingress.spec.tls:
        for tls in ingress.spec.tls:
            if not tls.secret_name:
                issues.append(f"TLS entry for {tls.hosts} missing secret_name")

    severity = "critical" if not status.load_balancer else "warning" if issues else "healthy"
    return {"issues": issues, "severity": severity}


# ─────────────────────────────────────────────
# WRITE OPERATIONS
# ─────────────────────────────────────────────

def create_ingress(
    name: str,
    namespace: str = "default",
    rules: Optional[list[dict]] = None,
    tls: Optional[list[dict]] = None,
    annotations: Optional[dict] = None,
    labels: Optional[dict] = None,
) -> dict:
    """
    Create a new Ingress.

    ⚠️  ACTION — requires user approval.

    Args:
        name:        Ingress name
        namespace:   Kubernetes namespace
        rules:       List of routing rules, each with: {"host": "example.com", "paths": [{"path": "/api", "service": "api-svc", "port": 8080}]}
        tls:         List of TLS configs: [{"hosts": ["example.com"], "secret_name": "tls-secret"}]
        annotations: Ingress annotations (e.g., {"nginx.ingress.kubernetes.io/rewrite-target": "/"})
        labels:      Dict of labels

    Returns:
        {"success": bool, "message": str}
    """
    from kubernetes import client
    from kubernetes.client import NetworkingV1Api

    if not rules:
        rules = []

    try:
        # Build HTTP rules
        http_rules = []
        for rule_dict in rules:
            host = rule_dict.get("host")
            paths = []
            for path_dict in rule_dict.get("paths", []):
                path_obj = client.V1HTTPIngressPath(
                    path=path_dict.get("path", "/"),
                    path_type="Prefix",
                    backend=client.V1IngressBackend(
                        service=client.V1IngressServiceBackend(
                            name=path_dict.get("service"),
                            port=client.V1ServiceBackendPort(number=path_dict.get("port", 80)),
                        )
                    ),
                )
                paths.append(path_obj)

            rule = client.V1IngressRule(host=host, http=client.V1HTTPIngressRuleValue(paths=paths))
            http_rules.append(rule)

        # Build TLS
        tls_objs = []
        if tls:
            for tls_dict in tls:
                tls_obj = client.V1IngressTLS(
                    secret_name=tls_dict.get("secret_name"),
                    hosts=tls_dict.get("hosts", []),
                )
                tls_objs.append(tls_obj)

        ingress_body = client.V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace,
                annotations=annotations or {},
                labels=labels or {},
            ),
            spec=client.V1IngressSpec(
                rules=http_rules,
                tls=tls_objs if tls_objs else None,
            ),
        )

        net_api = NetworkingV1Api()
        net_api.create_namespaced_ingress(namespace, ingress_body)
        logger.info(f"[ACTION] Created Ingress {namespace}/{name}")
        return {"success": True, "message": f"Ingress {namespace}/{name} created successfully."}
    except ApiException as e:
        logger.error(f"Failed to create Ingress {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def delete_ingress(name: str, namespace: str = "default") -> dict:
    """
    Delete an Ingress.

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    try:
        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        net_api.delete_namespaced_ingress(name, namespace)
        logger.info(f"[ACTION] Deleted Ingress {namespace}/{name}")
        return {"success": True, "message": f"Ingress {namespace}/{name} deleted."}
    except ApiException as e:
        logger.error(f"Failed to delete Ingress {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def patch_ingress(
    name: str, namespace: str = "default", labels: Optional[dict] = None, annotations: Optional[dict] = None
) -> dict:
    """
    Patch an Ingress (update labels/annotations).

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    if not labels and not annotations:
        return {"success": False, "message": "No labels or annotations provided."}

    try:
        patch_body = {}
        if labels:
            patch_body["metadata"] = {"labels": labels}
        if annotations:
            if "metadata" not in patch_body:
                patch_body["metadata"] = {}
            patch_body["metadata"]["annotations"] = annotations

        from kubernetes.client import NetworkingV1Api

        net_api = NetworkingV1Api()
        net_api.patch_namespaced_ingress(name, namespace, patch_body)
        logger.info(f"[ACTION] Patched Ingress {namespace}/{name}")
        return {"success": True, "message": f"Ingress {namespace}/{name} patched."}
    except ApiException as e:
        logger.error(f"Failed to patch Ingress {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_ingress(ingress) -> dict:
    """Convert Ingress object to clean dict."""
    spec = ingress.spec or {}
    status = ingress.status or {}

    # Extract hosts and paths
    hosts = []
    if spec.rules:
        for rule in spec.rules:
            if rule.host:
                hosts.append(rule.host)

    # Extract service backends
    backends = []
    if spec.rules:
        for rule in spec.rules:
            if rule.http and rule.http.paths:
                for path in rule.http.paths:
                    if path.backend and path.backend.service:
                        backends.append(
                            {
                                "service": path.backend.service.name,
                                "port": path.backend.service.port.number,
                                "path": path.path,
                            }
                        )

    # Extract ingress IP
    ingress_ip = None
    if status.load_balancer and status.load_balancer.ingress:
        for ing in status.load_balancer.ingress:
            ingress_ip = ing.ip or ing.hostname
            break

    # Extract TLS
    tls_hosts = []
    if spec.tls:
        for tls in spec.tls:
            tls_hosts.extend(tls.hosts or [])

    age = fmt_time(ingress.metadata.creation_timestamp) if ingress.metadata.creation_timestamp else None

    return {
        "name": ingress.metadata.name,
        "namespace": ingress.metadata.namespace,
        "hosts": hosts,
        "backends": backends,
        "ingress_ip": ingress_ip,
        "tls_hosts": tls_hosts,
        "age": age,
        "labels": ingress.metadata.labels or {},
    }
