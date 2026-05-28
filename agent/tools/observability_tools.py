"""
observability_tools.py — Metrics, logs, events, and pressure analysis.

Load this group when the agent needs to understand the current health
state of the cluster — CPU/memory usage, warning events, resource
pressure, and pod log tailing. Complements read_tools which handles
structural inspection.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ._client import AgentApiClient


def build_observability_tools(token: str) -> list:
    """Build metrics, logs, events, and pressure tools bound to the caller's token."""
    client = AgentApiClient(token)

    @tool
    def get_pod_metrics(name: str, namespace: str = "default") -> dict:
        """
        Get current CPU and memory usage for a specific pod.

        Returns live metrics from the metrics-server including CPU cores
        used, memory bytes used, and usage as a percentage of requests/limits.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/observability/metrics/pods/{name}", {"namespace": namespace})

    @tool
    def list_pod_metrics(namespace: str = "default") -> list:
        """
        Get current CPU and memory usage for all pods in a namespace.

        Useful for identifying the heaviest consumers before investigating
        resource pressure or proposing limit changes.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/observability/metrics/pods", {"namespace": namespace})

    @tool
    def get_node_metrics(name: str) -> dict:
        """
        Get current CPU and memory usage for a specific node.

        Returns live metrics including total used vs allocatable capacity.

        Args:
            name: Node name.
        """
        return client.get(f"/observability/metrics/nodes/{name}")

    @tool
    def list_node_metrics() -> list:
        """
        Get current CPU and memory usage for all nodes in the cluster.

        Use this to spot overloaded nodes before proposing a drain or
        investigating scheduling failures.
        """
        return client.get("/observability/metrics/nodes")

    @tool
    def get_resource_pressure(namespace: str = "default", threshold_pct: int | None = None) -> dict:
        """
        Get a resource pressure analysis for a namespace.

        Returns pods and containers that are close to or exceeding their
        CPU/memory limits. threshold_pct controls the sensitivity —
        lower values catch more pods.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
            threshold_pct: Report pods using more than this % of their limit.
                           Optional — omit to use the server default (80%).
        """
        params: dict = {"namespace": namespace}
        if threshold_pct is not None:
            params["threshold_pct"] = threshold_pct
        return client.get("/observability/resource-pressure", params)

    @tool
    def get_pod_metric_history(
        name: str,
        namespace: str = "default",
        metric: str = "cpu",
        duration_mins: int = 60,
    ) -> dict:
        """
        Get a time-series history of CPU or memory usage for a pod.

        Queries Prometheus for historical metric data. Use this to
        identify usage spikes, trends, or patterns over time.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            metric: Metric type — 'cpu' or 'memory'. Defaults to 'cpu'.
            duration_mins: How far back to look in minutes. Defaults to 60.
        """
        return client.get(
            f"/resources/pods/{namespace}/{name}/metrics/history",
            {"metric": metric, "duration_mins": duration_mins},
        )

    @tool
    def get_events(namespace: str = "default", severity: str = "warning", limit: int = 30) -> list:
        """
        Get Kubernetes events filtered by severity.

        Returns events with kind, name, namespace, reason, message,
        count, and timestamps. Use 'warning' to find problems and
        'normal' for informational events.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
            severity: Event severity filter — 'warning' or 'normal'. Defaults to 'warning'.
            limit: Maximum number of events to return. Defaults to 30.
        """
        return client.get("/events", {"namespace": namespace, "severity": severity, "limit": limit})

    @tool
    def get_warning_summary(namespace: str = "default", limit: int = 30) -> dict:
        """
        Get a summarized view of recent warning events in a namespace.

        Returns grouped warning counts by reason and affected resource,
        making it easier to spot systemic problems at a glance.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
            limit: Maximum number of events to include. Defaults to 30.
        """
        return client.get("/events/summary", {"namespace": namespace, "limit": limit})

    @tool
    def get_resource_events(kind: str, name: str, namespace: str = "default") -> list:
        """
        Get all Kubernetes events for a specific resource.

        More targeted than get_events — returns only events for the
        named resource. Useful for deep-diving into a single object.

        Args:
            kind: Resource kind e.g. 'Pod', 'Deployment', 'Node'.
            name: Resource name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/events/resources/{kind}/{name}", {"namespace": namespace})

    @tool
    def get_quota_pressure(namespace: str = "default") -> dict:
        """
        Get quota pressure analysis for a namespace.

        Returns ResourceQuota usage as a percentage of hard limits,
        highlighting quotas that are close to being exhausted.
        Use this before proposing resource-intensive actions.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/governance/quota-pressure", {"namespace": namespace})

    return [
        get_pod_metrics,
        list_pod_metrics,
        get_node_metrics,
        list_node_metrics,
        get_resource_pressure,
        get_pod_metric_history,
        get_events,
        get_warning_summary,
        get_resource_events,
        get_quota_pressure,
    ]
