"""
cluster_tools.py — Platform-level meta tools.

Load this group when the agent needs to inspect the audit trail,
check platform health, or get a broad cluster overview. These tools
operate at the platform level rather than on specific k8s resources.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ._client import AgentApiClient


def build_cluster_tools(token: str) -> list:
    """Build platform health and audit tools bound to the caller's token."""
    client = AgentApiClient(token)

    @tool
    def get_health() -> dict:
        """
        Check the health status of the AIOps platform itself.

        Returns API status, database connectivity, kubernetes connectivity,
        and monitoring component status. Use this if the agent suspects
        a platform issue rather than a cluster issue.
        """
        return client.get("/health")

    @tool
    def get_audit_logs(
        limit: int = 50,
        action_type: str | None = None,
        success: bool | None = None,
    ) -> list:
        """
        Retrieve recent audit log entries.

        Returns a list of actions taken through the platform including
        action type, target resource, namespace, user, source, status,
        and timestamp. Useful for investigating what changed recently
        and who made the change.

        Args:
            limit: Maximum number of entries to return. Defaults to 50.
            action_type: Filter by action type e.g. 'pod_delete', 'deployment_scale'.
                         Optional.
            success: Filter by outcome — True for successful actions only,
                     False for failures only. Optional — omit for all.
        """
        params: dict = {"limit": limit}
        if action_type:
            params["action_type"] = action_type
        if success is not None:
            params["success"] = str(success).lower()
        return client.get("/audit-logs", params)

    return [
        get_health,
        get_audit_logs,
    ]
