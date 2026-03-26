"""
Tools/ingresses.py

Ingress read operations.

Ingresses are a primary source of "why can't I reach my service from outside"
questions. This module lets the agent inspect routing rules, TLS config,
and whether the referenced backend services and their pods are healthy.

READ:
  - list_ingresses(namespace)           → all Ingresses with rules summary
  - get_ingress(name, namespace)        → single Ingress detail
  - diagnose_ingress(name, namespace)   → end-to-end health check of an Ingress
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1
from .utils import fmt_duration

logger = logging.getLogger(__name__)


def _get_networking_v1():
    from kubernetes import client
    from .client import _init_client
    _init_client()
    return client.NetworkingV1Api()


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_ingresses(namespace: str = "default") -> list[dict]:
    """
    List all Ingresses in a namespace with their hostnames, paths, and backends.

    Returns:
        [{"name": str, "namespace": str, "hosts": [...], "tls": bool, "age": str}]
    """
    net = _get_networking_v1()
    try:
        ing_list = net.list_namespaced_ingress(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list ingresses in {namespace}: {e}")
        raise
    return [_summarize_ingress(ing) for ing in ing_list.items]


def list_all_ingresses() -> list[dict]:
    """List Ingresses across ALL namespaces."""
    net = _get_networking_v1()
    try:
        ing_list = net.list_ingress_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all ingresses: {e}")
        raise
    return [_summarize_ingress(ing) for ing in ing_list.items]


def get_ingress(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single Ingress."""
    net = _get_networking_v1()
    try:
        ing = net.read_namespaced_ingress(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Ingress {namespace}/{name} not found: {e}")
        raise
    return _summarize_ingress(ing)


def diagnose_ingress(name: str, namespace: str = "default") -> dict:
    """
    End-to-end health check of an Ingress.

    Checks:
    1. Ingress exists and has rules
    2. Each backend Service exists
    3. Each backend Service has ready endpoints
    4. TLS secrets exist (if TLS is configured)

    This is the function the agent should call when a user says
    "why can't I reach my app from outside" or "my ingress isn't working".

    Returns:
        {
          "ingress":   {...},      # ingress summary
          "backend_checks": [...], # per-backend service health
          "tls_checks": [...],     # per-TLS-secret existence
          "issues": [...],
          "recommendations": [...],
        }
    """
    from .networking import check_service_endpoints
    from .secrets import secret_exists

    report = {
        "ingress":          {},
        "backend_checks":   [],
        "tls_checks":       [],
        "issues":           [],
        "recommendations":  [],
    }

    # Fetch the ingress
    try:
        ing = get_ingress(name, namespace)
        report["ingress"] = ing
    except ApiException:
        report["issues"].append(f"Ingress '{name}' not found in namespace '{namespace}'.")
        report["recommendations"].append("Check the ingress name and namespace.")
        return report

    if not ing.get("rules"):
        report["issues"].append("Ingress has no routing rules defined.")
        report["recommendations"].append("Add at least one rule with a host and path to the Ingress spec.")

    # Check each backend service
    checked_services = set()
    for rule in ing.get("rules", []):
        for path_entry in rule.get("paths", []):
            svc_name = path_entry.get("backend_service")
            if not svc_name or svc_name in checked_services:
                continue
            checked_services.add(svc_name)

            ep_check = check_service_endpoints(svc_name, namespace)
            backend_result = {
                "service":        svc_name,
                "host":           rule.get("host"),
                "path":           path_entry.get("path"),
                "service_exists": ep_check["service_exists"],
                "ready_endpoints": ep_check["endpoint_count"],
                "issues":         ep_check.get("issues", []),
            }
            report["backend_checks"].append(backend_result)

            if not ep_check["service_exists"]:
                report["issues"].append(
                    f"Backend service '{svc_name}' (for host '{rule.get('host')}') does not exist."
                )
                report["recommendations"].append(
                    f"Create service '{svc_name}' or update the Ingress backend to point to the correct service."
                )
            elif ep_check["endpoint_count"] == 0:
                report["issues"].append(
                    f"Backend service '{svc_name}' has no ready endpoints — backing pods may be down."
                )
                report["recommendations"].append(
                    f"Check that pods selected by service '{svc_name}' are running and passing readiness probes."
                )

    # Check TLS secrets
    for tls_entry in ing.get("tls", []):
        secret_name = tls_entry.get("secret_name")
        if not secret_name:
            report["issues"].append("TLS entry is missing a secretName.")
            report["recommendations"].append("Provide a valid TLS secret name in the Ingress spec.")
            continue

        exists = secret_exists(secret_name, namespace)
        tls_result = {
            "secret_name": secret_name,
            "hosts":       tls_entry.get("hosts", []),
            "exists":      exists,
        }
        report["tls_checks"].append(tls_result)

        if not exists:
            report["issues"].append(
                f"TLS secret '{secret_name}' not found — HTTPS will fail for hosts: {tls_entry.get('hosts', [])}."
            )
            report["recommendations"].append(
                f"Create the TLS secret '{secret_name}' with a valid certificate and key, "
                f"or use cert-manager to provision it automatically."
            )

    # Check ingress class annotation
    if not ing.get("ingress_class") and not ing.get("annotations", {}).get("kubernetes.io/ingress.class"):
        report["issues"].append(
            "No ingress class specified — the Ingress may not be picked up by any controller."
        )
        report["recommendations"].append(
            "Set spec.ingressClassName or the 'kubernetes.io/ingress.class' annotation."
        )

    if not report["issues"]:
        report["assessment"] = "Ingress appears healthy — all backends have ready endpoints."
    else:
        report["assessment"] = f"{len(report['issues'])} issue(s) found."

    return report


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_ingress(ing) -> dict:
    spec   = ing.spec
    meta   = ing.metadata
    creation = meta.creation_timestamp

    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    # Parse rules
    rules = []
    if spec and spec.rules:
        for rule in spec.rules:
            paths = []
            if rule.http and rule.http.paths:
                for p in rule.http.paths:
                    backend_svc = None
                    backend_port = None
                    if p.backend and p.backend.service:
                        backend_svc  = p.backend.service.name
                        backend_port = (
                            p.backend.service.port.number
                            if p.backend.service.port else None
                        )
                    paths.append({
                        "path":            p.path,
                        "path_type":       p.path_type,
                        "backend_service": backend_svc,
                        "backend_port":    backend_port,
                    })
            rules.append({
                "host":  rule.host,
                "paths": paths,
            })

    # TLS entries
    tls = []
    if spec and spec.tls:
        for t in spec.tls:
            tls.append({
                "hosts":       t.hosts or [],
                "secret_name": t.secret_name,
            })

    # Load-balancer IPs assigned by the ingress controller
    lb_ips = []
    if ing.status and ing.status.load_balancer and ing.status.load_balancer.ingress:
        for lb in ing.status.load_balancer.ingress:
            lb_ips.append(lb.ip or lb.hostname)

    return {
        "name":          meta.name,
        "namespace":     meta.namespace,
        "ingress_class": spec.ingress_class_name if spec else None,
        "rules":         rules,
        "tls":           tls,
        "lb_ips":        lb_ips,
        "annotations":   meta.annotations or {},
        "age":           age,
    }
