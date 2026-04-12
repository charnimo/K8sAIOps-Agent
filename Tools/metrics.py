"""
tools/metrics.py

Resource metrics collection via the Kubernetes Metrics Server.

READ:
  - get_pod_metrics(name, namespace)        → CPU/memory usage for a pod
  - get_node_metrics(name)                  → CPU/memory usage for a node
  - list_pod_metrics(namespace)             → all pods' metrics in a namespace
  - list_node_metrics()                     → all nodes' metrics
  - detect_resource_pressure(namespace)     → identify over/under-utilized workloads

NOTE:
  Metrics Server must be installed in the cluster.
  If it's not available, functions return a graceful "unavailable" response.

  Metrics Server API group: metrics.k8s.io/v1beta1
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_custom_objects
from .utils import parse_memory_mi, parse_cpu_m
from .config import RESOURCE_PRESSURE_THRESHOLD_PCT

logger = logging.getLogger(__name__)

_METRICS_GROUP   = "metrics.k8s.io"
_METRICS_VERSION = "v1beta1"


# ─────────────────────────────────────────────
# POD METRICS
# ─────────────────────────────────────────────

def get_pod_metrics(name: str, namespace: str = "default") -> dict:
    """
    Get current CPU and memory usage for a specific pod.

    Returns:
        {
          "name": "my-pod",
          "namespace": "default",
          "containers": [
            {"name": "app", "cpu": "25m", "memory": "128Mi"}
          ]
        }
    """
    custom = get_custom_objects()
    try:
        metrics = custom.get_namespaced_custom_object(
            group=_METRICS_GROUP,
            version=_METRICS_VERSION,
            namespace=namespace,
            plural="pods",
            name=name,
        )
        return _fmt_pod_metrics(metrics)
    except ApiException as e:
        if e.status == 404:
            return {"error": "Metrics not found — pod may not be running or Metrics Server unavailable."}
        logger.warning(f"Metrics Server error for pod {namespace}/{name}: {e.reason}")
        return {"error": f"Metrics unavailable: {e.reason}"}


def list_pod_metrics(namespace: str = "default") -> list[dict]:
    """
    Get CPU and memory usage for all pods in a namespace.

    Returns a list of pod metric dicts.
    """
    custom = get_custom_objects()
    try:
        result = custom.list_namespaced_custom_object(
            group=_METRICS_GROUP,
            version=_METRICS_VERSION,
            namespace=namespace,
            plural="pods",
        )
        return [_fmt_pod_metrics(item) for item in result.get("items", [])]
    except ApiException as e:
        logger.warning(f"Failed to list pod metrics in {namespace}: {e.reason}")
        return [{"error": f"Metrics unavailable: {e.reason}"}]


# ─────────────────────────────────────────────
# NODE METRICS
# ─────────────────────────────────────────────

def get_node_metrics(name: str) -> dict:
    """
    Get current CPU and memory usage for a specific node.

    Returns:
        {"name": "node-1", "cpu": "1200m", "memory": "4Gi"}
    """
    custom = get_custom_objects()
    try:
        metrics = custom.get_cluster_custom_object(
            group=_METRICS_GROUP,
            version=_METRICS_VERSION,
            plural="nodes",
            name=name,
        )
        return _fmt_node_metrics(metrics)
    except ApiException as e:
        logger.warning(f"Metrics Server error for node {name}: {e.reason}")
        return {"error": f"Metrics unavailable: {e.reason}"}


def list_node_metrics() -> list[dict]:
    """Get CPU and memory usage for all nodes in the cluster."""
    custom = get_custom_objects()
    try:
        result = custom.list_cluster_custom_object(
            group=_METRICS_GROUP,
            version=_METRICS_VERSION,
            plural="nodes",
        )
        return [_fmt_node_metrics(item) for item in result.get("items", [])]
    except ApiException as e:
        logger.warning(f"Failed to list node metrics: {e.reason}")
        return [{"error": f"Metrics unavailable: {e.reason}"}]


# ─────────────────────────────────────────────
# HIGH-LEVEL ANALYSIS
# ─────────────────────────────────────────────

def detect_resource_pressure(namespace: str = "default", threshold_pct: int = None) -> dict:
    """
    Compare live resource usage against declared limits to detect pressure.

    Returns:
        {
          "high_memory": [{"pod": "...", "container": "...", "usage": "450Mi", "limit": "512Mi", "pct": 87}],
          "high_cpu":    [...],
          "no_limits":   [{"pod": "...", "container": "..."}],   # containers with no limits set
        }

    Args:
        namespace:    Target namespace
        threshold_pct: Percentage threshold to trigger high-pressure alert (default: RESOURCE_PRESSURE_THRESHOLD_PCT)

    Note: Requires both Metrics Server (for usage) and deployment specs (for limits).
    """
    if threshold_pct is None:
        threshold_pct = RESOURCE_PRESSURE_THRESHOLD_PCT
    
    from .pods import list_pods  # local import to avoid circular dependency

    metrics_list = list_pod_metrics(namespace)
    pods_list    = list_pods(namespace)

    # Index metrics by pod name → container name → usage
    metrics_index: dict[str, dict[str, dict]] = {}
    metrics_errors = []  # Track pods where metrics collection failed
    for pm in metrics_list:
        if "error" in pm:
            # Log and track the error instead of silently skipping
            error_msg = pm.get("error", "Unknown error")
            logger.warning(f"Metrics unavailable for pod: {error_msg}")
            metrics_errors.append({
                "pod": pm.get("name", "unknown"),
                "error": error_msg
            })
            continue
        metrics_index[pm["name"]] = {
            c["name"]: c for c in pm.get("containers", [])
        }

    # Index pod resource specs by pod name → container name → limits
    limits_index: dict[str, dict[str, dict]] = {}
    for pod in pods_list:
        limits_index[pod["name"]] = {
            rs["name"]: rs.get("resources", {})
            for rs in pod.get("resource_specs", [])
        }

    high_memory = []
    high_cpu    = []
    no_limits   = []

    for pod_name, containers in metrics_index.items():
        for cname, usage_data in containers.items():
            limit_data = limits_index.get(pod_name, {}).get(cname, {})
            limits     = limit_data.get("limits", {})

            mem_usage = parse_memory_mi(usage_data.get("memory", "0"))
            cpu_usage = parse_cpu_m(usage_data.get("cpu", "0"))

            mem_limit_raw = limits.get("memory")
            cpu_limit_raw = limits.get("cpu")

            if not mem_limit_raw and not cpu_limit_raw:
                no_limits.append({"pod": pod_name, "container": cname})
                continue

            if mem_limit_raw:
                mem_limit = parse_memory_mi(mem_limit_raw)
                if mem_limit > 0:
                    pct = (mem_usage / mem_limit) * 100
                    if pct >= threshold_pct:
                        high_memory.append({
                            "pod":       pod_name,
                            "container": cname,
                            "usage":     usage_data.get("memory"),
                            "limit":     mem_limit_raw,
                            "pct":       round(pct, 1),
                        })

            if cpu_limit_raw:
                cpu_limit = parse_cpu_m(cpu_limit_raw)
                if cpu_limit > 0:
                    pct = (cpu_usage / cpu_limit) * 100
                    if pct >= threshold_pct:
                        high_cpu.append({
                            "pod":       pod_name,
                            "container": cname,
                            "usage":     usage_data.get("cpu"),
                            "limit":     cpu_limit_raw,
                            "pct":       round(pct, 1),
                        })

    # Sort by severity
    high_memory.sort(key=lambda x: x["pct"], reverse=True)
    high_cpu.sort(key=lambda x: x["pct"], reverse=True)

    return {
        "high_memory": high_memory,
        "high_cpu":    high_cpu,
        "no_limits":   no_limits,
        "metrics_errors": metrics_errors,  # Pods where metrics collection failed
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _fmt_pod_metrics(item: dict) -> dict:
    containers = []
    for c in item.get("containers", []):
        usage = c.get("usage", {})
        containers.append({
            "name":   c["name"],
            "cpu":    usage.get("cpu", "0"),
            "memory": usage.get("memory", "0"),
        })
    return {
        "name":       item["metadata"]["name"],
        "namespace":  item["metadata"].get("namespace", ""),
        "timestamp":  item.get("timestamp"),
        "containers": containers,
    }


def _fmt_node_metrics(item: dict) -> dict:
    usage = item.get("usage", {})
    return {
        "name":      item["metadata"]["name"],
        "timestamp": item.get("timestamp"),
        "cpu":       usage.get("cpu", "0"),
        "memory":    usage.get("memory", "0"),
    }


import os
import requests
import subprocess
import time
import atexit
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def get_prometheus_url() -> str:
    """Dynamically retrieve or proxy Prometheus for Minikube environments."""
    manual_url = os.environ.get("PROMETHEUS_URL")
    if manual_url:
        return manual_url
        
    try:
        # Check if port-forward is already running
        resp = requests.get("http://127.0.0.1:9090/-/ready", timeout=1)
        if resp.status_code == 200:
            return "http://127.0.0.1:9090"
    except Exception:
        pass

    try:
        node_ip = subprocess.check_output(
            ["kubectl", "get", "nodes", "-o", "jsonpath={.items[0].status.addresses[0].address}"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        
        node_port = subprocess.check_output(
            ["kubectl", "get", "services", "prometheus-server", "-n", "monitoring", "-o", "jsonpath={.spec.ports[0].nodePort}"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        
        if node_ip and node_port:
            url = f"http://{node_ip}:{node_port}"
            # Test if reachable (will fail on Minikube Linux/Docker without tunnel)
            try:
                requests.get(f"{url}/-/ready", timeout=1)
                return url
            except requests.exceptions.RequestException:
                pass
    except Exception:
        pass
        
    # If we got here, we're likely on Linux Docker driver where Node IP is unroutable.
    # Automatically spawn a background port-forward process.
    try:
        logger.info("Spawning background kubectl port-forward for Prometheus on port 9090...")
        pf_process = subprocess.Popen(
            ["kubectl", "port-forward", "-n", "monitoring", "svc/prometheus-server", "9090:80"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Kill the port-forward when Uvicorn/app exits
        atexit.register(lambda: pf_process.terminate())
        
        # Wait a brief moment to ensure the tunnel establishes
        time.sleep(2)
        return "http://127.0.0.1:9090"
    except Exception as e:
        logger.error(f"Failed to auto-start port-forward: {e}")

    return "http://127.0.0.1:9090"

PROMETHEUS_URL = get_prometheus_url()

def query_prometheus(query_expr: str) -> Dict[str, Any]:
    """Execute an instant query against the Prometheus API."""
    url = f"{PROMETHEUS_URL}/api/v1/query"
    try:
        response = requests.get(url, params={"query": query_expr}, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Prometheus query failed: {e}")
        return {"status": "error", "error": str(e), "data": None}

def query_prometheus_range(query_expr: str, start: str, end: str, step: str) -> Dict[str, Any]:
    """Execute a range query (for charts/graphs) against the Prometheus API."""
    url = f"{PROMETHEUS_URL}/api/v1/query_range"
    params = {
        "query": query_expr,
        "start": start,
        "end": end,
        "step": step
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Prometheus range query failed: {e}")
        return {"status": "error", "error": str(e), "data": None}

def get_pod_metric_history(pod_name: str, namespace: str, metric_type: str = "cpu", duration_mins: int = 60, step: str = "1m"):
    """Template for a specific Prometheus query: Pod metrics history."""
    
    if metric_type == "memory":
        query = f'sum(container_memory_working_set_bytes{{pod="{pod_name}", namespace="{namespace}"}}) by (pod)'
    elif metric_type == "network_receive":
        query = f'sum(rate(container_network_receive_bytes_total{{pod="{pod_name}", namespace="{namespace}"}}[5m])) by (pod)'
    elif metric_type == "network_transmit":
        query = f'sum(rate(container_network_transmit_bytes_total{{pod="{pod_name}", namespace="{namespace}"}}[5m])) by (pod)'
    else: # cpu
        query = f'sum(rate(container_cpu_usage_seconds_total{{pod="{pod_name}", namespace="{namespace}"}}[5m])) by (pod)'
    
    # Calculate start and end times dynamically in UNIX timestamps using Python
    import time
    end_time = int(time.time())
    start_time = end_time - (duration_mins * 60)
    
    response = query_prometheus_range(query, str(start_time), str(end_time), step)
    
    # If the metrics are missing (common with cAdvisor network metrics on some CNIs/Minikube),
    # pad the output with zero values so the frontend chart doesn't break or hang.
    if response and response.get("status") == "success" and response.get("data"):
        if not response["data"].get("result"):
            def parse_step_to_seconds(s: str) -> int:
                unit, val = s[-1], int(s[:-1])
                if unit == 's': return val
                if unit == 'm': return val * 60
                if unit == 'h': return val * 3600
                if unit == 'd': return val * 86400
                return val
            
            step_secs = parse_step_to_seconds(step)
            timestamps = list(range(start_time, end_time + 1, step_secs))
            
            response["data"]["result"] = [{
                "metric": {"pod": pod_name, "namespace": namespace, "_synthetic": "true"},
                "values": [[ts, "0"] for ts in timestamps]
            }]
            
    return response
