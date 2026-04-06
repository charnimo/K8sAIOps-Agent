"""
tools/hpa.py

Kubernetes HorizontalPodAutoscaler (HPA) operations for auto-scaling deployments.

Operations:
  READ:  list_hpas, get_hpa, detect_hpa_issues
  WRITE: create_hpa, delete_hpa, patch_hpa
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .utils import fmt_time

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────

def list_hpas(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """
    List HorizontalPodAutoscalers in a namespace.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label filter

    Returns:
        List of HPA summaries with target, min/max replicas, current metrics
    """
    try:
        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        hpas = auto_api.list_namespaced_horizontal_pod_autoscaler(namespace, label_selector=label_selector)
        return [_summarize_hpa(hpa) for hpa in hpas.items]
    except ApiException as e:
        logger.error(f"Failed to list HPAs in {namespace}: {e}")
        return []


def list_all_hpas(label_selector: Optional[str] = None) -> list[dict]:
    """List HPAs across all namespaces."""
    try:
        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        hpas = auto_api.list_horizontal_pod_autoscaler_for_all_namespaces(label_selector=label_selector)
        return [_summarize_hpa(hpa) for hpa in hpas.items]
    except ApiException as e:
        logger.error(f"Failed to list all HPAs: {e}")
        return []


def get_hpa(name: str, namespace: str = "default") -> dict:
    """Get a single HorizontalPodAutoscaler."""
    try:
        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        hpa = auto_api.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        return _summarize_hpa(hpa)
    except ApiException as e:
        logger.error(f"Failed to get HPA {namespace}/{name}: {e}")
        return {"error": str(e)}


def detect_hpa_issues(name: str, namespace: str = "default") -> dict:
    """
    Detect issues with an HPA (scaling failures, metrics unavailable, etc.).

    Returns:
        {"issues": [str], "severity": "healthy" | "warning" | "critical"}
    """
    try:
        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        hpa = auto_api.read_namespaced_horizontal_pod_autoscaler(name, namespace)
    except ApiException as e:
        return {"issues": [f"HPA not found: {e}"], "severity": "critical"}

    issues = []
    status = hpa.status or {}

    # Check conditions
    if hpa.status and hpa.status.conditions:
        for cond in hpa.status.conditions:
            if cond.status != "True":
                issues.append(f"{cond.type}: {cond.message}")

    # Check if scaling is active
    if status.current_replicas is not None:
        min_replicas = hpa.spec.min_replicas or 1
        max_replicas = hpa.spec.max_replicas or 10
        current = status.current_replicas

        if current < min_replicas:
            issues.append(f"Current replicas ({current}) below minimum ({min_replicas})")
        elif current > max_replicas:
            issues.append(f"Current replicas ({current}) exceeds maximum ({max_replicas})")

    severity = "critical" if any("ScalingActive=False" in iss for iss in issues) else "warning" if issues else "healthy"
    return {"issues": issues, "severity": severity}


# ─────────────────────────────────────────────
# WRITE OPERATIONS
# ─────────────────────────────────────────────

def create_hpa(
    name: str,
    namespace: str = "default",
    target_kind: str = "Deployment",
    target_name: str = "",
    min_replicas: int = 1,
    max_replicas: int = 10,
    target_cpu_percent: Optional[int] = None,
    target_memory_percent: Optional[int] = None,
    labels: Optional[dict] = None,
) -> dict:
    """
    Create a new HorizontalPodAutoscaler.

    ⚠️  ACTION — requires user approval.

    Args:
        name:                   HPA name
        namespace:              Kubernetes namespace
        target_kind:            "Deployment" (default), "StatefulSet", "ReplicaSet"
        target_name:            Name of the target workload to scale
        min_replicas:           Minimum pod count (default: 1)
        max_replicas:           Maximum pod count (default: 10)
        target_cpu_percent:     Target CPU utilization % (optional)
        target_memory_percent:  Target memory utilization % (optional)
        labels:                 Dict of labels

    Returns:
        {"success": bool, "message": str}
    """
    from kubernetes import client
    from kubernetes.client import AutoscalingV2Api

    if not target_name:
        return {"success": False, "message": "target_name is required."}

    try:
        # Build metrics
        metrics = []
        if target_cpu_percent:
            metrics.append(
                client.V2MetricSpec(
                    type="Resource",
                    resource=client.V2ResourceMetricSource(
                        name="cpu",
                        target=client.V2MetricTarget(
                            type="Utilization",
                            average_utilization=target_cpu_percent,
                        ),
                    ),
                )
            )

        if target_memory_percent:
            metrics.append(
                client.V2MetricSpec(
                    type="Resource",
                    resource=client.V2ResourceMetricSource(
                        name="memory",
                        target=client.V2MetricTarget(
                            type="Utilization",
                            average_utilization=target_memory_percent,
                        ),
                    ),
                )
            )

        # Default to CPU 80% if no metrics specified
        if not metrics:
            metrics.append(
                client.V2MetricSpec(
                    type="Resource",
                    resource=client.V2ResourceMetricSource(
                        name="cpu",
                        target=client.V2MetricTarget(
                            type="Utilization",
                            average_utilization=80,
                        ),
                    ),
                )
            )

        hpa_body = client.V2HorizontalPodAutoscaler(
            api_version="autoscaling/v2",
            kind="HorizontalPodAutoscaler",
            metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels or {}),
            spec=client.V2HorizontalPodAutoscalerSpec(
                scale_target_ref=client.V2CrossVersionObjectReference(
                    api_version="apps/v1",
                    kind=target_kind,
                    name=target_name,
                ),
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                metrics=metrics if metrics else None,
            ),
        )

        auto_api = AutoscalingV2Api()
        auto_api.create_namespaced_horizontal_pod_autoscaler(namespace, hpa_body)
        logger.info(f"[ACTION] Created HPA {namespace}/{name} for {target_kind}/{target_name}")
        return {"success": True, "message": f"HPA {namespace}/{name} created successfully."}
    except ApiException as e:
        logger.error(f"Failed to create HPA {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def delete_hpa(name: str, namespace: str = "default") -> dict:
    """
    Delete a HorizontalPodAutoscaler.

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    try:
        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        auto_api.delete_namespaced_horizontal_pod_autoscaler(name, namespace)
        logger.info(f"[ACTION] Deleted HPA {namespace}/{name}")
        return {"success": True, "message": f"HPA {namespace}/{name} deleted."}
    except ApiException as e:
        logger.error(f"Failed to delete HPA {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def patch_hpa(
    name: str,
    namespace: str = "default",
    min_replicas: Optional[int] = None,
    max_replicas: Optional[int] = None,
    labels: Optional[dict] = None,
) -> dict:
    """
    Patch an HPA (update scaling limits or labels).

    ⚠️  ACTION — requires user approval.

    Returns:
        {"success": bool, "message": str}
    """
    if not any([min_replicas is not None, max_replicas is not None, labels]):
        return {"success": False, "message": "No updates provided."}

    try:
        patch_body = {}

        if min_replicas is not None or max_replicas is not None:
            patch_body["spec"] = {}
            if min_replicas is not None:
                patch_body["spec"]["minReplicas"] = min_replicas
            if max_replicas is not None:
                patch_body["spec"]["maxReplicas"] = max_replicas

        if labels:
            if "metadata" not in patch_body:
                patch_body["metadata"] = {}
            patch_body["metadata"]["labels"] = labels

        from kubernetes.client import AutoscalingV2Api

        auto_api = AutoscalingV2Api()
        auto_api.patch_namespaced_horizontal_pod_autoscaler(name, namespace, patch_body)
        logger.info(f"[ACTION] Patched HPA {namespace}/{name}")
        return {"success": True, "message": f"HPA {namespace}/{name} patched."}
    except ApiException as e:
        logger.error(f"Failed to patch HPA {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_hpa(hpa) -> dict:
    """Convert HPA object to clean dict."""
    spec = hpa.spec or {}
    status = hpa.status or {}

    # Extract metrics
    metrics = []
    if spec.metrics:
        for metric in spec.metrics:
            if metric.type == "Resource" and metric.resource:
                metrics.append(
                    {
                        "type": "Resource",
                        "resource": metric.resource.name,
                        "target_utilization": metric.resource.target.average_utilization,
                    }
                )

    # Scale target ref
    target = spec.scale_target_ref or {}

    age = fmt_time(hpa.metadata.creation_timestamp) if hpa.metadata.creation_timestamp else None

    return {
        "name": hpa.metadata.name,
        "namespace": hpa.metadata.namespace,
        "target": f"{target.kind}/{target.name}" if target else "N/A",
        "min_replicas": spec.min_replicas or 1,
        "max_replicas": spec.max_replicas or 10,
        "current_replicas": status.current_replicas,
        "desired_replicas": status.desired_replicas,
        "metrics": metrics,
        "conditions": [
            {"type": c.type, "status": c.status, "message": c.message}
            for c in (status.conditions or [])
        ],
        "age": age,
        "labels": hpa.metadata.labels or {},
    }
