"""
k8s_client/networking.py

Network-related read operations:
  - check_service_endpoints(name, namespace)     → verify service has ready endpoints
  - list_services(namespace)                     → list all services
  - check_network_policies(namespace)            → list network policies and assess impact
  - diagnose_network(source_pod, target_service, namespace) → connectivity diagnosis
  - diagnose_database_connection(pod, namespace) → DB connectivity analysis
  - get_service(name, namespace)                 → service details + selector match check
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_core_v1

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SERVICE OPERATIONS
# ─────────────────────────────────────────────

def list_services(namespace: str = "default") -> list[dict]:
    """List all services in a namespace with their type, ports, and selector."""
    core = get_core_v1()
    try:
        svc_list = core.list_namespaced_service(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list services in {namespace}: {e}")
        raise

    result = []
    for svc in svc_list.items:
        ports = []
        if svc.spec.ports:
            for p in svc.spec.ports:
                ports.append({
                    "name":        p.name,
                    "port":        p.port,
                    "target_port": str(p.target_port) if p.target_port else None,
                    "protocol":    p.protocol,
                })
        result.append({
            "name":        svc.metadata.name,
            "namespace":   svc.metadata.namespace,
            "type":        svc.spec.type,
            "cluster_ip":  svc.spec.cluster_ip,
            "ports":       ports,
            "selector":    svc.spec.selector or {},
        })
    return result


def get_service(name: str, namespace: str = "default") -> dict:
    """Fetch a single service and check if it has a valid selector and matching pods."""
    core = get_core_v1()
    try:
        svc = core.read_namespaced_service(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Service {namespace}/{name} not found: {e}")
        raise

    selector = svc.spec.selector or {}
    ports = []
    if svc.spec.ports:
        for p in svc.spec.ports:
            ports.append({
                "name":        p.name,
                "port":        p.port,
                "target_port": str(p.target_port) if p.target_port else None,
                "protocol":    p.protocol,
            })

    # Check how many pods match the selector
    matching_pods = 0
    if selector:
        label_selector = ",".join(f"{k}={v}" for k, v in selector.items())
        try:
            pod_list = core.list_namespaced_pod(
                namespace=namespace,
                label_selector=label_selector,
            )
            matching_pods = len(pod_list.items)
        except ApiException:
            pass

    return {
        "name":          svc.metadata.name,
        "namespace":     svc.metadata.namespace,
        "type":          svc.spec.type,
        "cluster_ip":    svc.spec.cluster_ip,
        "external_ip":   svc.spec.external_i_ps,
        "ports":         ports,
        "selector":      selector,
        "matching_pods": matching_pods,
        "has_selector":  bool(selector),
    }


def check_service_endpoints(name: str, namespace: str = "default") -> dict:
    """
    Verify that a service has ready endpoints (i.e. backing pods are healthy).

    Returns:
        {
          "service_exists": bool,
          "endpoint_count": int,
          "ready_addresses": [...],
          "not_ready_addresses": [...],
          "issues": ["NoEndpoints" | "SelectorMismatch" | "PodsNotReady"],
        }
    """
    core = get_core_v1()
    issues = []

    # Check service exists
    try:
        svc_info = get_service(name, namespace)
    except ApiException:
        return {
            "service_exists":      False,
            "endpoint_count":      0,
            "ready_addresses":     [],
            "not_ready_addresses": [],
            "issues":              [f"Service '{name}' not found in namespace '{namespace}'"],
        }

    if not svc_info["has_selector"]:
        issues.append("NoSelector — service has no pod selector (headless or external)")

    # Fetch endpoints
    try:
        ep = core.read_namespaced_endpoints(name=name, namespace=namespace)
    except ApiException:
        return {
            "service_exists":      True,
            "service_info":        svc_info,
            "endpoint_count":      0,
            "ready_addresses":     [],
            "not_ready_addresses": [],
            "issues":              ["EndpointsNotFound"],
        }

    ready_addrs     = []
    not_ready_addrs = []

    if ep.subsets:
        for subset in ep.subsets:
            if subset.addresses:
                for addr in subset.addresses:
                    ready_addrs.append({
                        "ip":  addr.ip,
                        "pod": addr.target_ref.name if addr.target_ref else None,
                    })
            if subset.not_ready_addresses:
                for addr in subset.not_ready_addresses:
                    not_ready_addrs.append({
                        "ip":  addr.ip,
                        "pod": addr.target_ref.name if addr.target_ref else None,
                    })

    if not ready_addrs and not not_ready_addrs:
        issues.append("NoEndpoints — no pods match the service selector")
        if svc_info["matching_pods"] == 0:
            issues.append("SelectorMismatch — service selector matches 0 pods")
    elif not ready_addrs and not_ready_addrs:
        issues.append("PodsNotReady — pods exist but none are in Ready state")

    return {
        "service_exists":      True,
        "service_info":        svc_info,
        "endpoint_count":      len(ready_addrs),
        "ready_addresses":     ready_addrs,
        "not_ready_addresses": not_ready_addrs,
        "issues":              issues,
    }


# ─────────────────────────────────────────────
# NETWORK POLICIES
# ─────────────────────────────────────────────

def check_network_policies(namespace: str = "default") -> dict:
    """
    List network policies in a namespace and assess their potential impact.

    Returns:
        {
          "count": int,
          "policies": [...],
          "warnings": ["Policy X may be blocking ingress to service Y", ...]
        }
    """
    from kubernetes import client as k8s_client
    from .client import get_core_v1
    _init_networking_v1()

    try:
        netpol_list = _net_v1().list_namespaced_network_policy(namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {"count": 0, "policies": [], "warnings": ["NetworkPolicy API not available in this cluster"]}
        logger.error(f"Failed to list network policies in {namespace}: {e}")
        raise

    policies = []
    warnings = []

    for np in netpol_list.items:
        ingress_rules = []
        egress_rules  = []

        if np.spec.ingress:
            for rule in np.spec.ingress:
                ingress_rules.append({
                    "from":  [str(f) for f in (rule._from or [])],
                    "ports": [{"port": p.port, "protocol": p.protocol} for p in (rule.ports or [])],
                })
        if np.spec.egress:
            for rule in np.spec.egress:
                egress_rules.append({
                    "to":    [str(t) for t in (rule.to or [])],
                    "ports": [{"port": p.port, "protocol": p.protocol} for p in (rule.ports or [])],
                })

        policy_types = np.spec.policy_types or []

        # Warn about deny-all patterns
        if "Ingress" in policy_types and not np.spec.ingress:
            warnings.append(
                f"Policy '{np.metadata.name}' denies ALL ingress to pods matching "
                f"{np.spec.pod_selector.match_labels}"
            )
        if "Egress" in policy_types and not np.spec.egress:
            warnings.append(
                f"Policy '{np.metadata.name}' denies ALL egress from pods matching "
                f"{np.spec.pod_selector.match_labels}"
            )

        policies.append({
            "name":          np.metadata.name,
            "namespace":     np.metadata.namespace,
            "pod_selector":  np.spec.pod_selector.match_labels or {},
            "policy_types":  policy_types,
            "ingress_rules": ingress_rules,
            "egress_rules":  egress_rules,
        })

    return {
        "count":    len(policies),
        "policies": policies,
        "warnings": warnings,
    }


# ─────────────────────────────────────────────
# NETWORK DIAGNOSTICS
# ─────────────────────────────────────────────

def diagnose_network(
    source_pod: str,
    target_service: str,
    namespace: str = "default",
) -> dict:
    """
    Diagnose network connectivity between a pod and a service.

    Performs static analysis (no actual ping/curl) by checking:
    1. Source pod exists and is running
    2. Target service exists
    3. Service has ready endpoints
    4. Network policies might be blocking traffic
    5. Service selector matches target pods

    Returns a connectivity assessment with issues and recommendations.
    """
    from .pods import get_pod_status

    report = {
        "source_pod":     source_pod,
        "target_service": target_service,
        "namespace":      namespace,
        "checks":         {},
        "issues":         [],
        "recommendations": [],
    }

    # Check 1: Source pod
    try:
        pod_status = get_pod_status(source_pod, namespace)
        report["checks"]["source_pod"] = {
            "status": "ok" if pod_status["phase"] == "Running" else "problem",
            "phase":  pod_status["phase"],
            "ready":  pod_status["ready"],
        }
        if pod_status["phase"] != "Running":
            report["issues"].append(f"Source pod '{source_pod}' is not Running (phase: {pod_status['phase']})")
    except Exception as e:
        report["checks"]["source_pod"] = {"status": "not_found", "error": str(e)}
        report["issues"].append(f"Source pod '{source_pod}' not found")

    # Check 2: Service endpoints
    ep_check = check_service_endpoints(target_service, namespace)
    report["checks"]["service_endpoints"] = ep_check
    if not ep_check["service_exists"]:
        report["issues"].append(f"Target service '{target_service}' does not exist")
        report["recommendations"].append(f"Create service '{target_service}' or check the service name")
    elif ep_check["endpoint_count"] == 0:
        report["issues"].append(f"Service '{target_service}' has no ready endpoints")
        report["recommendations"].append("Check if backing pods are running and their readiness probes pass")
    for issue in ep_check.get("issues", []):
        report["issues"].append(issue)

    # Check 3: Network policies
    try:
        netpol = check_network_policies(namespace)
        report["checks"]["network_policies"] = {
            "count":    netpol["count"],
            "warnings": netpol["warnings"],
        }
        for warning in netpol["warnings"]:
            report["issues"].append(f"NetworkPolicy: {warning}")
            report["recommendations"].append(
                "Review NetworkPolicy rules — a deny-all policy may be blocking traffic"
            )
    except Exception as e:
        report["checks"]["network_policies"] = {"error": str(e)}

    # Overall assessment
    if not report["issues"]:
        report["assessment"] = "No static connectivity issues detected. Problem may be application-level."
    else:
        report["assessment"] = f"{len(report['issues'])} connectivity issue(s) found."

    return report


def diagnose_database_connection(
    pod_name: str,
    namespace: str = "default",
    db_service_name: Optional[str] = None,
) -> dict:
    """
    Diagnose database connectivity issues from a pod.

    Analyzes:
    1. Pod logs for common DB connection error patterns
    2. Database service existence and endpoints
    3. Missing DB-related environment variables / secrets
    4. Network policies blocking DB port

    Returns a structured diagnosis with root causes and suggested fixes.
    """
    from .pods import get_pod_logs, get_pod_status, get_pod
    from .events import get_events_for_resource

    report = {
        "pod_name":        pod_name,
        "namespace":       namespace,
        "db_service":      db_service_name,
        "log_patterns":    [],
        "missing_env":     [],
        "service_check":   {},
        "issues":          [],
        "recommendations": [],
    }

    # Common DB error log patterns
    DB_ERROR_PATTERNS = [
        ("connection refused",          "DB service unreachable — service may not exist or wrong port"),
        ("connection timed out",        "DB service timeout — check network policies and service name"),
        ("no such host",                "DNS resolution failed — check DB_HOST environment variable"),
        ("authentication failed",       "Wrong credentials — check DB_PASSWORD / DB_USER in secrets"),
        ("password authentication",     "Wrong credentials — check DB_PASSWORD in secrets"),
        ("database does not exist",     "Wrong database name — check DB_NAME environment variable"),
        ("too many connections",        "DB connection pool exhausted — check max_connections"),
        ("ssl connection required",     "SSL configuration mismatch — check DB SSL settings"),
        ("connect: connection refused", "DB pod may be down or wrong host/port"),
    ]

    # Analyze logs for DB error patterns
    try:
        logs = get_pod_logs(pod_name, namespace, tail_lines=200)
        logs_lower = logs.lower()
        for pattern, explanation in DB_ERROR_PATTERNS:
            if pattern in logs_lower:
                report["log_patterns"].append({
                    "pattern":     pattern,
                    "explanation": explanation,
                })
                report["issues"].append(explanation)
    except Exception as e:
        report["log_patterns"] = [{"error": str(e)}]

    # Check DB-related env vars in pod spec
    try:
        pod = get_pod(pod_name, namespace)
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                env_names = [e.name for e in (container.env or [])]
                env_from  = [ef.config_map_ref.name if ef.config_map_ref else
                             ef.secret_ref.name if ef.secret_ref else "?"
                             for ef in (container.env_from or [])]

                DB_ENV_KEYS = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER",
                               "DB_PASSWORD", "DATABASE_URL", "POSTGRES_URI",
                               "MYSQL_HOST", "MONGO_URI", "REDIS_URL"]

                found = [k for k in DB_ENV_KEYS if k in env_names]
                missing = [k for k in ["DB_HOST", "DB_NAME"] if k not in env_names and
                           "DATABASE_URL" not in env_names and "POSTGRES_URI" not in env_names]

                report["env_analysis"] = {
                    "found_db_vars": found,
                    "missing_likely": missing,
                    "env_from_sources": env_from,
                }

                if missing:
                    for m in missing:
                        report["issues"].append(f"Missing environment variable: {m}")
                    report["recommendations"].append(
                        "Add missing DB environment variables to the deployment spec or ConfigMap"
                    )
    except Exception as e:
        report["env_analysis"] = {"error": str(e)}

    # Check DB service if name provided
    if db_service_name:
        ep_check = check_service_endpoints(db_service_name, namespace)
        report["service_check"] = ep_check
        if not ep_check["service_exists"]:
            report["issues"].append(f"Database service '{db_service_name}' not found")
            report["recommendations"].append(
                f"Create database service '{db_service_name}' or fix DB_HOST to match actual service name"
            )
        elif ep_check["endpoint_count"] == 0:
            report["issues"].append(f"Database service '{db_service_name}' has no ready pods")
            report["recommendations"].append(
                "Check database pod health — it may be crashed or still starting"
            )

    # Add generic recommendations based on log patterns
    if not report["recommendations"] and report["log_patterns"]:
        report["recommendations"].append("Check DB credentials in secrets and verify DB_HOST points to correct service")

    if not report["issues"]:
        report["issues"].append("No obvious DB connectivity errors found in logs")
        report["recommendations"].append("Try increasing log verbosity in the application to see more detail")

    return report


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

_networking_v1_client = None

def _init_networking_v1():
    global _networking_v1_client
    if _networking_v1_client is None:
        from kubernetes import client as k8s_client
        from .client import _init_client
        _init_client()
        _networking_v1_client = k8s_client.NetworkingV1Api()

def _net_v1():
    _init_networking_v1()
    return _networking_v1_client
