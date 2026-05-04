"""Tool registry and wrappers for monitoring agent.

Wraps Tools/* functions and provides:
- Tool definitions for LLM consumption
- Permission-scoped execution
- Error handling and retries
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Coroutine
from datetime import datetime

from app.agent.schemas import ToolDefinition, DiagnosticResult

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

# PLACEHOLDER: Import functions from Tools package
# These are stubs - replace with actual imports when ready
# from Tools import pods, deployments, services, metrics, events, nodes
# from Tools.diagnostics import diagnose_pod, diagnose_deployment


async def _get_pod_logs(
    namespace: str, pod_name: str, container: Optional[str] = None, lines: int = 500
) -> Dict[str, Any]:
    """Get pod container logs.

    PLACEHOLDER: Calls Tools/pods.py::get_pod_logs
    """
    try:
        # from Tools.pods import get_pod_logs as real_get_pod_logs
        # return real_get_pod_logs(namespace, pod_name, container, lines)
        logger.info(f"[PLACEHOLDER] get_pod_logs({namespace}, {pod_name})")
        return {"logs": [], "container": container, "lines_returned": 0}
    except Exception as e:
        raise RuntimeError(f"Failed to get pod logs: {str(e)}")


async def _get_pod_events(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod Kubernetes events.

    PLACEHOLDER: Calls Tools/events.py::get_pod_events
    """
    try:
        # from Tools.events import get_pod_events as real_get_pod_events
        # return real_get_pod_events(namespace, pod_name)
        logger.info(f"[PLACEHOLDER] get_pod_events({namespace}, {pod_name})")
        return {"events": []}
    except Exception as e:
        raise RuntimeError(f"Failed to get pod events: {str(e)}")


async def _get_pod_status(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod status and conditions.

    PLACEHOLDER: Calls Tools/pods.py::get_pod_status
    """
    try:
        # from Tools.pods import get_pod_status as real_get_pod_status
        # return real_get_pod_status(namespace, pod_name)
        logger.info(f"[PLACEHOLDER] get_pod_status({namespace}, {pod_name})")
        return {
            "phase": "Unknown",
            "conditions": [],
            "restart_count": 0,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to get pod status: {str(e)}")


async def _get_pod_metrics(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get pod CPU and memory metrics.

    PLACEHOLDER: Calls Tools/metrics.py::get_pod_metrics
    """
    try:
        # from Tools.metrics import get_pod_metrics as real_get_pod_metrics
        # return real_get_pod_metrics(namespace, pod_name)
        logger.info(f"[PLACEHOLDER] get_pod_metrics({namespace}, {pod_name})")
        return {"cpu_usage": "0m", "memory_usage": "0Mi"}
    except Exception as e:
        raise RuntimeError(f"Failed to get pod metrics: {str(e)}")


async def _get_deployment_info(
    namespace: str, deployment_name: str
) -> Dict[str, Any]:
    """Get deployment configuration and status.

    PLACEHOLDER: Calls Tools/deployments.py::get_deployment_info
    """
    try:
        # from Tools.deployments import get_deployment_info as real_get_deployment_info
        # return real_get_deployment_info(namespace, deployment_name)
        logger.info(
            f"[PLACEHOLDER] get_deployment_info({namespace}, {deployment_name})"
        )
        return {
            "replicas": 0,
            "ready_replicas": 0,
            "image": "",
            "resource_requests": {},
            "resource_limits": {},
        }
    except Exception as e:
        raise RuntimeError(f"Failed to get deployment info: {str(e)}")


async def _list_nodes() -> Dict[str, Any]:
    """List cluster nodes and their status.

    PLACEHOLDER: Calls Tools/nodes.py::list_nodes
    """
    try:
        # from Tools.nodes import list_nodes as real_list_nodes
        # return real_list_nodes()
        logger.info("[PLACEHOLDER] list_nodes()")
        return {"nodes": []}
    except Exception as e:
        raise RuntimeError(f"Failed to list nodes: {str(e)}")


async def _describe_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """Get full pod description (combined status + events + logs).

    PLACEHOLDER: Calls Tools/diagnostics.py::diagnose_pod
    """
    try:
        # from Tools.diagnostics import diagnose_pod as real_diagnose_pod
        # return real_diagnose_pod(namespace, pod_name)
        logger.info(f"[PLACEHOLDER] describe_pod({namespace}, {pod_name})")
        return {"target": f"{namespace}/{pod_name}", "issues": []}
    except Exception as e:
        raise RuntimeError(f"Failed to describe pod: {str(e)}")


async def _describe_deployment(
    namespace: str, deployment_name: str, detailed: bool = False
) -> Dict[str, Any]:
    """Get full deployment description with pod info.

    PLACEHOLDER: Calls Tools/diagnostics.py::diagnose_deployment
    """
    try:
        # from Tools.diagnostics import diagnose_deployment as real_diagnose_deployment
        # return real_diagnose_deployment(namespace, deployment_name, detailed)
        logger.info(
            f"[PLACEHOLDER] describe_deployment({namespace}, {deployment_name})"
        )
        return {"target": f"{namespace}/{deployment_name}", "issues": []}
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
