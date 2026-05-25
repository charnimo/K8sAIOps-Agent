"""Tool registry and wrappers for monitoring agent.

Wraps the existing Tools/* functions and provides:
- Tool definitions for LLM consumption
- Permission-scoped execution
- Error handling and retries
"""

import asyncio
import importlib
import inspect
import logging
import os
import pkgutil
import sys
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from Tools.deployments import get_deployment, get_deployment_events
from Tools.diagnostics import diagnose_deployment, diagnose_pod
from Tools.hpa import detect_hpa_issues, get_hpa
from Tools.metrics import get_pod_metrics
from Tools.nodes import list_nodes
from Tools.pods import get_pod_events, get_pod_logs, get_pod_status
from Tools.pods import delete_pod, exec_pod
from Tools.deployments import patch_resource_limits, scale_deployment, rollout_restart

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
# DYNAMIC TOOL LOADING FROM Tools PACKAGE
# ============================================================================

def _python_type_to_schema(annotation: Any) -> Dict[str, Any]:
    if annotation in (int, float):
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is dict:
        return {"type": "object"}
    if annotation in (list, tuple, set):
        return {"type": "array"}
    return {"type": "string"}


def _infer_tool_category(name: str) -> str:
    name = name.lower()
    if name.startswith(("create", "delete", "patch", "scale", "rollout", "rollback", "restart", "exec", "cordon", "uncordon", "drain", "resume", "suspend", "apply", "update")):
        return "action"
    return "diagnostics"


def _infer_tool_read_only(name: str) -> bool:
    return _infer_tool_category(name) != "action"


def _infer_permission_required(name: str) -> Optional[str]:
    # Simple heuristic; actual permission mapping may be enhanced later.
    if name.startswith("get") or name.startswith("list") or name.startswith("describe") or name.startswith("detect"):
        return None
    if name.startswith("create"):
        return "create"
    if name.startswith(("delete", "patch", "scale", "rollout", "rollback", "restart", "exec", "cordon", "uncordon", "drain", "resume", "suspend", "update")):
        return "modify"
    return None


def _build_tool_parameters(func: Callable) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    try:
        signature = inspect.signature(func)
    except (ValueError, TypeError):
        return params

    for name, param in signature.parameters.items():
        if name == "self" or param.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            continue
        schema = _python_type_to_schema(param.annotation)
        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default
        params[name] = schema
    return params


def _load_tools_from_package(exclude: Optional[set[str]] = None) -> Dict[str, Tool]:
    exclude = exclude or set()
    tools: Dict[str, Tool] = {}

    package_name = "Tools"
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        return tools

    # Ensure the repository root is on sys.path for Tools imports.
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    for finder, module_name, ispkg in pkgutil.iter_modules(package.__path__, package_name + "."):
        short_name = module_name.split(".")[-1]
        if short_name in {"client", "config", "utils", "audit"}:
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for attr_name, attr_value in vars(module).items():
            if attr_name.startswith("_"):
                continue
            if attr_name in exclude:
                continue
            if not inspect.isfunction(attr_value):
                continue
            if attr_value.__module__ != module_name:
                continue

            tool = Tool(
                name=attr_name,
                func=attr_value,
                description=f"Tool wrapper for {module_name}.{attr_name}",
                category=_infer_tool_category(attr_name),
                parameters=_build_tool_parameters(attr_value),
                permission_required=_infer_permission_required(attr_name),
                is_read_only=_infer_tool_read_only(attr_name),
            )
            tools[attr_name] = tool
    return tools



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


async def _get_hpa_info(namespace: str, hpa_name: str) -> Dict[str, Any]:
    """Get HPA status and target information."""
    try:
        return {"hpa": get_hpa(name=hpa_name, namespace=namespace)}
    except Exception as e:
        raise RuntimeError(f"Failed to get HPA info: {str(e)}")


async def _detect_hpa_issues(namespace: str, hpa_name: str) -> Dict[str, Any]:
    """Detect HPA scaling and metrics issues."""
    try:
        return detect_hpa_issues(name=hpa_name, namespace=namespace)
    except Exception as e:
        raise RuntimeError(f"Failed to detect HPA issues: {str(e)}")


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
    "get_hpa_info": Tool(
        name="get_hpa_info",
        func=_get_hpa_info,
        description="Get HorizontalPodAutoscaler target, replicas, and conditions",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "hpa_name": {"type": "string", "description": "HorizontalPodAutoscaler name"},
        },
        is_read_only=True,
    ),
    "detect_hpa_issues": Tool(
        name="detect_hpa_issues",
        func=_detect_hpa_issues,
        description="Detect HPA scaling issues such as missing metrics or inactive scaling",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "hpa_name": {"type": "string", "description": "HorizontalPodAutoscaler name"},
        },
        is_read_only=True,
    ),
    # Action / remediation tools (require explicit approval to execute)
    "restart_pod": Tool(
        name="restart_pod",
        func=lambda namespace, pod_name: delete_pod(name=pod_name, namespace=namespace),
        description="Restart a pod by deleting it (controller will recreate) — ACTION",
        category="action",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
        },
        permission_required="pods:delete",
        is_read_only=False,
    ),
    "exec_pod": Tool(
        name="exec_pod",
        func=lambda namespace, pod_name, command: exec_pod(name=pod_name, namespace=namespace, command=command),
        description="Execute a command inside a pod (ACTION, dangerous)",
        category="action",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "pod_name": {"type": "string", "description": "Pod name"},
            "command": {"type": "string", "description": "Command to run in pod"},
        },
        permission_required="pods:exec",
        is_read_only=False,
    ),
    "scale_deployment": Tool(
        name="scale_deployment",
        func=lambda namespace, deployment_name, replicas: scale_deployment(name=deployment_name, namespace=namespace, replicas=replicas),
        description="Scale a deployment to desired replica count (ACTION)",
        category="action",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "deployment_name": {"type": "string", "description": "Deployment name"},
            "replicas": {"type": "integer", "description": "Desired replica count"},
        },
        permission_required="deployments:scale",
        is_read_only=False,
    ),
    "rollout_restart": Tool(
        name="rollout_restart",
        func=lambda namespace, deployment_name: rollout_restart(name=deployment_name, namespace=namespace),
        description="Trigger a rolling restart of a deployment (ACTION)",
        category="action",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "deployment_name": {"type": "string", "description": "Deployment name"},
        },
        permission_required="deployments:restart",
        is_read_only=False,
    ),
    "patch_resource_limits": Tool(
        name="patch_resource_limits",
        func=lambda namespace, deployment_name, container_name=None, cpu_request=None, cpu_limit=None, memory_request=None, memory_limit=None: patch_resource_limits(
            name=deployment_name,
            namespace=namespace,
            container_name=container_name,
            cpu_request=cpu_request,
            cpu_limit=cpu_limit,
            memory_request=memory_request,
            memory_limit=memory_limit,
        ),
        description="Patch CPU/memory requests and limits for a deployment container (ACTION)",
        category="action",
        parameters={
            "namespace": {"type": "string", "description": "Kubernetes namespace"},
            "deployment_name": {"type": "string", "description": "Deployment name"},
            "container_name": {"type": "string", "description": "Container name (optional if single container)"},
            "cpu_request": {"type": "string", "description": "CPU request, e.g. 250m"},
            "cpu_limit": {"type": "string", "description": "CPU limit, e.g. 500m"},
            "memory_request": {"type": "string", "description": "Memory request, e.g. 256Mi"},
            "memory_limit": {"type": "string", "description": "Memory limit, e.g. 512Mi"},
        },
        permission_required="deployments:patch",
        is_read_only=False,
    ),
}

# Dynamically add any additional Tools/* functions not explicitly wrapped above.
try:
    MONITORING_TOOL_REGISTRY.update(_load_tools_from_package(exclude=set(MONITORING_TOOL_REGISTRY.keys())))
except Exception:
    logger.warning("Failed to dynamically load additional Tools package functions")


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
