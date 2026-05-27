"""
diagnostic_tools.py — Active diagnosis and issue detection.

Load this group when the agent needs to run structured diagnostics
on a resource or the cluster as a whole. These tools go beyond
listing — they actively analyze health, connectivity, and readiness.

Distinct from observability_tools (which is metrics/events) and
read_tools (which is structural inspection). Diagnostics synthesize
multiple data sources into a single actionable assessment.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ._client import AgentApiClient


def build_diagnostic_tools(token: str) -> list:
    client = AgentApiClient(token)

    @tool
    def diagnose_pod(name: str, namespace: str = "default") -> dict:
        """
        Run a full diagnostic on a pod.

        Synthesizes status, events, logs, resource usage, and issue
        classification into a single structured report with a root
        cause assessment and recommended remediation steps.

        Use this as the first tool when a user reports a pod problem
        rather than calling list_pods + get_pod separately.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/diagnostics/pods", {"name": name, "namespace": namespace})

    @tool
    def diagnose_deployment(
        name: str,
        namespace: str = "default",
        include_pod_details: bool = False,
        include_resource_pressure: bool = False,
    ) -> dict:
        """
        Run a full diagnostic on a deployment.

        Analyzes replica counts, rollout status, pod readiness, events,
        and optionally pod-level details and resource pressure.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            include_pod_details: Include per-pod diagnostics. Increases
                                 response size. Default False.
            include_resource_pressure: Include resource pressure analysis
                                       for the deployment's pods. Default False.
        """
        return client.get("/diagnostics/deployments", {
            "name": name,
            "namespace": namespace,
            "include_pod_details": str(include_pod_details).lower(),
            "include_resource_pressure": str(include_resource_pressure).lower(),
        })

    @tool
    def diagnose_service(name: str, namespace: str = "default") -> dict:
        """
        Run a full diagnostic on a service.

        Checks endpoint health, selector matching, port configuration,
        and connectivity issues. Useful for diagnosing traffic routing
        problems.

        Args:
            name: Service name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/diagnostics/services", {"name": name, "namespace": namespace})

    @tool
    def diagnose_cluster(namespace: str = "default") -> dict:
        """
        Run a cluster-wide diagnostic.

        Returns a high-level health summary including node status,
        failing workloads, resource pressure hotspots, and warning
        event counts across the cluster or a specific namespace.

        Args:
            namespace: Scope the diagnostic to a namespace. Defaults to 'default'.
                       God-mode users can pass 'all' for cluster-wide scope.
        """
        return client.get("/diagnostics/cluster", {"namespace": namespace})

    @tool
    def get_namespace_events(name: str, limit: int = 100) -> list:
        """
        Get all recent events in a namespace.

        Broader than get_resource_events — returns everything happening
        in the namespace. Useful for cluster-wide incident triage.

        Args:
            name: Namespace name.
            limit: Maximum number of events to return. Default 100.
        """
        return client.get(f"/cluster/namespaces/{name}/events", {"limit": limit})

    @tool
    def get_network_policy_issues(namespace: str = "default") -> dict:
        """
        Get a network policy issue analysis for a namespace.

        Detects misconfigured policies, overly permissive rules,
        orphaned policies with no matching pods, and connectivity
        gaps between services.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/config/network-policies/issues", {"namespace": namespace})

    @tool
    def get_dashboard_summary(namespace: str = "default") -> dict:
        """
        Get a high-level cluster summary for a namespace.

        Returns counts of healthy vs unhealthy pods, deployments,
        services, and nodes, plus recent warning events. Good as
        a first-call orientation tool when the user asks a general
        'what's going on' question.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/dashboard/summary", {"namespace": namespace})


    @tool
    def get_recent_incidents(severity: str = None, limit: int = 5, namespace: str = None) -> list:
        """
        Get a list of recent automated incidents detected by the passive AI monitor.
        Use this to find out what went wrong in the cluster recently.
        Returns a compact summary (ID, resource, severity, summary, status).
        
        Args:
            severity: Filter by 'CRITICAL' or 'WARNING' (optional).
            limit: Number of incidents to return. Defaults to 5.
            namespace: Filter by namespace (optional).
        """
        params = {"limit": limit}
        if severity: params["severity"] = severity
        if namespace: params["namespace"] = namespace
        
        res = client.get("/events/incidents", params)
        if isinstance(res, list):
            # Condense the payload to save tokens
            return [{
                "incident_id": r.get("incident_id"),
                "severity": r.get("severity"),
                "resource": f"{r.get('namespace')}/{r.get('resource_name')}",
                "status": r.get("status"),
                "summary": r.get("summary")
            } for r in res]
        return res

    @tool
    def get_incident_details(incident_id: str) -> dict:
        """
        Get the full AI diagnostic report, root cause analysis, and remediation plan 
        for a specific incident ID (e.g. 'inc_1234567890').
        
        Use this before attempting to fix an incident to understand exactly what the 
        background monitor discovered and what steps it recommends.
        """
        res = client.get(f"/events/incidents/{incident_id}")
        if isinstance(res, dict):
            # Drop the massive log snapshot to save LLM context window space;
            # The root_cause_analysis already summarizes the log findings.
            res.pop("log_snapshot", None)
            res.pop("collected_diagnostics", None)
        return res

    return [
        diagnose_pod,        get_recent_incidents,
        get_incident_details,

        diagnose_deployment,
        diagnose_service,
        diagnose_cluster,
        get_namespace_events,
        get_network_policy_issues,
        get_dashboard_summary,
    ]
