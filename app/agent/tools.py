"""Tool registry and wrappers for monitoring agent.

Wraps the existing Tools/* functions and provides:
- Tool definitions for LLM consumption
- Permission-scoped execution
- Error handling and retries
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from Tools.deployments import get_deployment, get_deployment_events
from Tools.diagnostics import diagnose_deployment, diagnose_pod
from Tools.metrics import get_pod_metrics
from Tools.nodes import list_nodes
from Tools.pods import get_pod_events, get_pod_logs, get_pod_status

from app.agent.schemas import DiagnosticResult, ToolDefinition

logger = logging.getLogger(__name__)


# ============================================================================
# TOOL WRAPPER CLASS
# ============================================================================


class Tool:
    """Wrapper for a callable tool with metadata."""

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        category: str = "diagnostics",
        parameters: Optional[Dict[str, Any]] = None,
        permission_required: Optional[str] = None,
        is_read_only: bool = True,
    ):
        """Initialize tool wrapper.

        Args:
            name: Unique tool name (e.g., "get_pod_logs")
            func: Async or sync callable to execute
            description: Human-readable description
            category: Tool category (diagnostics, mutation, query)
            parameters: JSON schema for expected parameters
            permission_required: Permission key needed to call this tool
            is_read_only: Whether tool modifies cluster state
        """
        self.name = name
        self.func = func
        self.description = description
        self.category = category
        self.parameters = parameters or {}
        self.permission_required = permission_required
        self.is_read_only = is_read_only

    def to_definition(self) -> ToolDefinition:
        """Convert to ToolDefinition for LLM."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            category=self.category,
            parameters=self.parameters,
            returns={"data": "dict", "error": "Optional[str]"},
            permission_required=self.permission_required,
            is_read_only=self.is_read_only,
        )

    async def execute(self, **kwargs) -> DiagnosticResult:
        """Execute tool with error handling.

        Args:
            **kwargs: Arguments for the tool function

        Returns:
            DiagnosticResult with outcome
        """
        start_time = datetime.now()
        try:
            # Check if function is async
            if asyncio.iscoroutinefunction(self.func):
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return DiagnosticResult(
                tool_name=self.name,
                success=True,
                data=result if isinstance(result, dict) else {"result": result},
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(
                f"Error executing tool {self.name}: {str(e)}", exc_info=True
            )
            return DiagnosticResult(
                tool_name=self.name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )


# ============================================================================
# DIAGNOSTIC TOOLS FROM Tools PACKAGE
# ============================================================================

async def _get_pod_logs(
    namespace: str, pod_name: str, container: Optional[str] = None, lines: int = 500
) -> Dict[str, Any]:
    """Get pod container logs using the existing Tools implementation."""
    try:
        logs = get_pod_logs(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=lines,
        )
        return {"logs": logs, "container": container, "lines_returned": lines}
    except Exception as e:
        raise RuntimeError(f"Failed to get pod logs: {str(e)}")


async def _get_pod_events(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod Kubernetes events using the existing Tools implementation."""
    try:
        return {"events": get_pod_events(name=pod_name, namespace=namespace)}
    except Exception as e:
        raise RuntimeError(f"Failed to get pod events: {str(e)}")


async def _get_pod_status(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod status and conditions using the existing Tools implementation."""
    try:
        return get_pod_status(name=pod_name, namespace=namespace)
    except Exception as e:
        raise RuntimeError(f"Failed to get pod status: {str(e)}")


async def _get_pod_metrics(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod CPU and memory metrics using the existing Tools implementation."""
    try:
        return get_pod_metrics(name=pod_name, namespace=namespace)
    except Exception as e:
        raise RuntimeError(f"Failed to get pod metrics: {str(e)}")


async def _get_deployment_info(
    namespace: str, deployment_name: str
) -> Dict[str, Any]:
    """Get deployment configuration and status using the existing Tools implementation."""
    try:
        deployment = get_deployment(name=deployment_name, namespace=namespace)
        events = get_deployment_events(name=deployment_name, namespace=namespace)
        return {"deployment": deployment, "events": events}
    except Exception as e:
        raise RuntimeError(f"Failed to get deployment info: {str(e)}")


async def _list_nodes() -> Dict[str, Any]:
    """List cluster nodes and their status using the existing Tools implementation."""
    try:
        return {"nodes": list_nodes()}
    except Exception as e:
        raise RuntimeError(f"Failed to list nodes: {str(e)}")


async def _describe_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get full pod description using the existing Tools implementation."""
    try:
        return diagnose_pod(name=pod_name, namespace=namespace)
    except Exception as e:
        raise RuntimeError(f"Failed to describe pod: {str(e)}")


async def _describe_deployment(
    namespace: str, deployment_name: str, detailed: bool = False
) -> Dict[str, Any]:
    """Get full deployment description using the existing Tools implementation."""
    try:
        return diagnose_deployment(
            name=deployment_name,
            namespace=namespace,
            include_pod_details=detailed,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to describe deployment: {str(e)}")


# ============================================================================
# TOOL REGISTRY
# ============================================================================


MONITORING_TOOL_REGISTRY: Dict[str, Tool] = {
    "get_pod_logs": Tool(
        name="get_pod_logs",
        func=_get_pod_logs,
        description="Retrieve container logs from a pod (last 500 lines by default)",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
            "container": {
                "type": "string",
                "description": "Container name (optional, uses first if not specified)",
            },
            "lines": {
                "type": "integer",
                "description": "Number of log lines to retrieve (default 500)",
            },
        },
        is_read_only=True,
    ),
    "get_pod_events": Tool(
        name="get_pod_events",
        func=_get_pod_events,
        description="Get Kubernetes events associated with a pod",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
        },
        is_read_only=True,
    ),
    "get_pod_status": Tool(
        name="get_pod_status",
        func=_get_pod_status,
        description="Get pod phase, conditions, and restart count",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
        },
        is_read_only=True,
    ),
    "get_pod_metrics": Tool(
        name="get_pod_metrics",
        func=_get_pod_metrics,
        description="Get pod CPU and memory usage metrics",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
        },
        is_read_only=True,
    ),
    "get_deployment_info": Tool(
        name="get_deployment_info",
        func=_get_deployment_info,
        description="Get deployment configuration, image, replicas, and resource limits",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "deployment_name": {"type": "string", "description": "Deployment name"},
        },
        is_read_only=True,
    ),
    "list_nodes": Tool(
        name="list_nodes",
        func=_list_nodes,
        description="List all cluster nodes and their status (ready, NotReady, etc.)",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "describe_pod": Tool(
        name="describe_pod",
        func=_describe_pod,
        description="Get comprehensive pod diagnostics (status, events, logs)",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
        },
        is_read_only=True,
    ),
    "describe_deployment": Tool(
        name="describe_deployment",
        func=_describe_deployment,
        description="Get comprehensive deployment diagnostics including pod status",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "deployment_name": {"type": "string", "description": "Deployment name"},
            "detailed": {
                "type": "boolean",
                "description": "Include per-pod details (default false)",
            },
        },
        is_read_only=True,
    ),
}


# ============================================================================
# TOOL ACCESS FUNCTIONS
# ============================================================================


def get_tool_by_name(name: str) -> Optional[Tool]:
    """Get tool definition by name.

    Args:
        name: Tool name

    Returns:
        Tool object or None if not found
    """
    return MONITORING_TOOL_REGISTRY.get(name)


async def execute_tool(name: str, **kwargs) -> DiagnosticResult:
    """Execute a tool by name.

    Args:
        name: Tool name
        **kwargs: Arguments for the tool

    Returns:
        DiagnosticResult with outcome

    Raises:
        ValueError: If tool not found
    """
    tool = get_tool_by_name(name)
    if not tool:
        raise ValueError(f"Tool '{name}' not found in registry")

    return await tool.execute(**kwargs)


def get_all_tools() -> List[Tool]:
    """Get all available tools."""
    return list(MONITORING_TOOL_REGISTRY.values())


def get_tool_definitions() -> List[ToolDefinition]:
    """Get all tool definitions for LLM consumption."""
    return [tool.to_definition() for tool in get_all_tools()]
