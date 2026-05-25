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

import Tools.configmaps as configmaps
import Tools.daemonsets as daemonsets
import Tools.deployments as deployments
import Tools.diagnostics as diagnostics
import Tools.events as events
import Tools.hpa as hpa
import Tools.ingress as ingress
import Tools.jobs as jobs
import Tools.metrics as metrics
import Tools.namespaces as namespaces
import Tools.network_policies as network_policies
import Tools.nodes as nodes
import Tools.pods as pods
import Tools.rbac as rbac
import Tools.resource_quotas as resource_quotas
import Tools.secrets as secrets
import Tools.services as services
import Tools.statefulsets as statefulsets
import Tools.storage as storage

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
    "create_configmap": Tool(
        name="create_configmap",
        func=configmaps.create_configmap,
        description="Create configmap",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "data": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_configmap": Tool(
        name="delete_configmap",
        func=configmaps.delete_configmap,
        description="Delete configmap",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_configmap": Tool(
        name="get_configmap",
        func=configmaps.get_configmap,
        description="Get configmap",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_configmaps": Tool(
        name="list_configmaps",
        func=configmaps.list_configmaps,
        description="List configmaps",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "patch_configmap": Tool(
        name="patch_configmap",
        func=configmaps.patch_configmap,
        description="Patch configmap",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "data": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_daemonset_issues": Tool(
        name="detect_daemonset_issues",
        func=daemonsets.detect_daemonset_issues,
        description="Detect daemonset issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_daemonset": Tool(
        name="get_daemonset",
        func=daemonsets.get_daemonset,
        description="Get daemonset",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_daemonsets": Tool(
        name="list_all_daemonsets",
        func=daemonsets.list_all_daemonsets,
        description="List all daemonsets",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_daemonsets": Tool(
        name="list_daemonsets",
        func=daemonsets.list_daemonsets,
        description="List daemonsets",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "restart_daemonset": Tool(
        name="restart_daemonset",
        func=daemonsets.restart_daemonset,
        description="Restart daemonset",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "update_daemonset_image": Tool(
        name="update_daemonset_image",
        func=daemonsets.update_daemonset_image,
        description="Update daemonset image",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "container": {"type": "string", "default": None},
            "image": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_deployment": Tool(
        name="get_deployment",
        func=deployments.get_deployment,
        description="Get deployment",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_deployment_events": Tool(
        name="get_deployment_events",
        func=deployments.get_deployment_events,
        description="Get deployment events",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_deployment_revisions": Tool(
        name="get_deployment_revisions",
        func=deployments.get_deployment_revisions,
        description="Get deployment revisions",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_deployments": Tool(
        name="list_all_deployments",
        func=deployments.list_all_deployments,
        description="List all deployments",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_deployments": Tool(
        name="list_deployments",
        func=deployments.list_deployments,
        description="List deployments",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "patch_env_var": Tool(
        name="patch_env_var",
        func=deployments.patch_env_var,
        description="Patch env var",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "container_name": {"type": "string", "default": None},
            "key": {"type": "string", "default": ''},
            "value": {"type": "string", "default": ''},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "rollback_deployment": Tool(
        name="rollback_deployment",
        func=deployments.rollback_deployment,
        description="Rollback deployment",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "revision": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "rollout_history": Tool(
        name="rollout_history",
        func=deployments.rollout_history,
        description="Rollout history",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "rollout_status": Tool(
        name="rollout_status",
        func=deployments.rollout_status,
        description="Rollout status",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "cluster_health_snapshot": Tool(
        name="cluster_health_snapshot",
        func=diagnostics.cluster_health_snapshot,
        description="Get a cluster health snapshot",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "diagnose_deployment": Tool(
        name="diagnose_deployment",
        func=diagnostics.diagnose_deployment,
        description="Diagnose deployment",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "include_pod_details": {"type": "boolean", "default": False},
            "include_resource_pressure": {"type": "boolean", "default": False},
        },
        is_read_only=True,
    ),
    "diagnose_pod": Tool(
        name="diagnose_pod",
        func=diagnostics.diagnose_pod,
        description="Diagnose pod",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "diagnose_service": Tool(
        name="diagnose_service",
        func=diagnostics.diagnose_service,
        description="Diagnose service",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "quick_summary": Tool(
        name="quick_summary",
        func=diagnostics.quick_summary,
        description="Quick summary",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "get_events_for_resource": Tool(
        name="get_events_for_resource",
        func=events.get_events_for_resource,
        description="Get events for resource",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "kind": {"type": "string", "default": 'Pod'},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_recent_warning_summary": Tool(
        name="get_recent_warning_summary",
        func=events.get_recent_warning_summary,
        description="Get recent warning summary",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": None},
            "limit": {"type": "number", "default": 20},
        },
        is_read_only=True,
    ),
    "list_all_events": Tool(
        name="list_all_events",
        func=events.list_all_events,
        description="List all events",
        category="diagnostics",
        parameters={
            "limit": {"type": "number", "default": 200},
        },
        is_read_only=True,
    ),
    "list_events": Tool(
        name="list_events",
        func=events.list_events,
        description="List events",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "limit": {"type": "number", "default": 100},
        },
        is_read_only=True,
    ),
    "list_warning_events": Tool(
        name="list_warning_events",
        func=events.list_warning_events,
        description="List warning events",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": None},
            "limit": {"type": "number", "default": 100},
        },
        is_read_only=True,
    ),
    "sort_events": Tool(
        name="sort_events",
        func=events.sort_events,
        description="Sort events",
        category="diagnostics",
        parameters={
            "events": {"type": "string"},
        },
        is_read_only=True,
    ),
    "create_hpa": Tool(
        name="create_hpa",
        func=hpa.create_hpa,
        description="Create hpa",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "target_kind": {"type": "string", "default": 'Deployment'},
            "target_name": {"type": "string", "default": ''},
            "min_replicas": {"type": "number", "default": 1},
            "max_replicas": {"type": "number", "default": 10},
            "target_cpu_percent": {"type": "string", "default": None},
            "target_memory_percent": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_hpa": Tool(
        name="delete_hpa",
        func=hpa.delete_hpa,
        description="Delete hpa",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_hpa": Tool(
        name="get_hpa",
        func=hpa.get_hpa,
        description="Get hpa",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_hpas": Tool(
        name="list_all_hpas",
        func=hpa.list_all_hpas,
        description="List all hpas",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_hpas": Tool(
        name="list_hpas",
        func=hpa.list_hpas,
        description="List hpas",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "patch_hpa": Tool(
        name="patch_hpa",
        func=hpa.patch_hpa,
        description="Patch hpa",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "min_replicas": {"type": "string", "default": None},
            "max_replicas": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "create_ingress": Tool(
        name="create_ingress",
        func=ingress.create_ingress,
        description="Create ingress",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "rules": {"type": "string", "default": None},
            "tls": {"type": "string", "default": None},
            "annotations": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_ingress": Tool(
        name="delete_ingress",
        func=ingress.delete_ingress,
        description="Delete ingress",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_ingress_issues": Tool(
        name="detect_ingress_issues",
        func=ingress.detect_ingress_issues,
        description="Detect ingress issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_ingress": Tool(
        name="get_ingress",
        func=ingress.get_ingress,
        description="Get ingress",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_ingresses": Tool(
        name="list_all_ingresses",
        func=ingress.list_all_ingresses,
        description="List all ingresses",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_ingresses": Tool(
        name="list_ingresses",
        func=ingress.list_ingresses,
        description="List ingresses",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "patch_ingress": Tool(
        name="patch_ingress",
        func=ingress.patch_ingress,
        description="Patch ingress",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "labels": {"type": "string", "default": None},
            "annotations": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "delete_job": Tool(
        name="delete_job",
        func=jobs.delete_job,
        description="Delete job",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "propagation_policy": {"type": "string", "default": 'Foreground'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_job_issues": Tool(
        name="detect_job_issues",
        func=jobs.detect_job_issues,
        description="Detect job issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_cronjob": Tool(
        name="get_cronjob",
        func=jobs.get_cronjob,
        description="Get cronjob",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_job": Tool(
        name="get_job",
        func=jobs.get_job,
        description="Get job",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_cronjobs": Tool(
        name="list_all_cronjobs",
        func=jobs.list_all_cronjobs,
        description="List all cronjobs",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "list_all_jobs": Tool(
        name="list_all_jobs",
        func=jobs.list_all_jobs,
        description="List all jobs",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_cronjobs": Tool(
        name="list_cronjobs",
        func=jobs.list_cronjobs,
        description="List cronjobs",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_jobs": Tool(
        name="list_jobs",
        func=jobs.list_jobs,
        description="List jobs",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "resume_cronjob": Tool(
        name="resume_cronjob",
        func=jobs.resume_cronjob,
        description="Resume cronjob",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "resume_job": Tool(
        name="resume_job",
        func=jobs.resume_job,
        description="Resume job",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "suspend_cronjob": Tool(
        name="suspend_cronjob",
        func=jobs.suspend_cronjob,
        description="Suspend cronjob",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "suspend_job": Tool(
        name="suspend_job",
        func=jobs.suspend_job,
        description="Suspend job",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_resource_pressure": Tool(
        name="detect_resource_pressure",
        func=metrics.detect_resource_pressure,
        description="Detect resource pressure",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "threshold_pct": {"type": "number", "default": None},
        },
        is_read_only=True,
    ),
    "get_node_metrics": Tool(
        name="get_node_metrics",
        func=metrics.get_node_metrics,
        description="Get node metrics",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_pod_metric_history": Tool(
        name="get_pod_metric_history",
        func=metrics.get_pod_metric_history,
        description="Get pod metric history",
        category="diagnostics",
        parameters={
            "pod_name": {"type": "string"},
            "namespace": {"type": "string"},
            "metric_type": {"type": "string", "default": 'cpu'},
            "duration_mins": {"type": "number", "default": 60},
            "step": {"type": "string", "default": '1m'},
        },
        is_read_only=True,
    ),
    "get_prometheus_url": Tool(
        name="get_prometheus_url",
        func=metrics.get_prometheus_url,
        description="Get prometheus url",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "list_node_metrics": Tool(
        name="list_node_metrics",
        func=metrics.list_node_metrics,
        description="List node metrics",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "list_pod_metrics": Tool(
        name="list_pod_metrics",
        func=metrics.list_pod_metrics,
        description="List pod metrics",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "query_prometheus": Tool(
        name="query_prometheus",
        func=metrics.query_prometheus,
        description="Query prometheus",
        category="diagnostics",
        parameters={
            "query_expr": {"type": "string"},
        },
        is_read_only=True,
    ),
    "query_prometheus_range": Tool(
        name="query_prometheus_range",
        func=metrics.query_prometheus_range,
        description="Query prometheus range",
        category="diagnostics",
        parameters={
            "query_expr": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
            "step": {"type": "string"},
        },
        is_read_only=True,
    ),
    "create_namespace": Tool(
        name="create_namespace",
        func=namespaces.create_namespace,
        description="Create namespace",
        category="action",
        parameters={
            "name": {"type": "string"},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_namespace": Tool(
        name="delete_namespace",
        func=namespaces.delete_namespace,
        description="Delete namespace",
        category="action",
        parameters={
            "name": {"type": "string"},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_namespace": Tool(
        name="get_namespace",
        func=namespaces.get_namespace,
        description="Get namespace",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_namespace_events": Tool(
        name="get_namespace_events",
        func=namespaces.get_namespace_events,
        description="Get namespace events",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "limit": {"type": "number", "default": 100},
        },
        is_read_only=True,
    ),
    "get_namespace_resource_count": Tool(
        name="get_namespace_resource_count",
        func=namespaces.get_namespace_resource_count,
        description="Get namespace resource count",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string"},
        },
        is_read_only=True,
    ),
    "list_namespaces": Tool(
        name="list_namespaces",
        func=namespaces.list_namespaces,
        description="List namespaces",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "detect_network_issues": Tool(
        name="detect_network_issues",
        func=network_policies.detect_network_issues,
        description="Detect network issues",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_network_policy": Tool(
        name="get_network_policy",
        func=network_policies.get_network_policy,
        description="Get network policy",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_network_policies": Tool(
        name="list_all_network_policies",
        func=network_policies.list_all_network_policies,
        description="List all network policies",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_network_policies": Tool(
        name="list_network_policies",
        func=network_policies.list_network_policies,
        description="List network policies",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "cordon_node": Tool(
        name="cordon_node",
        func=nodes.cordon_node,
        description="Cordon node",
        category="action",
        parameters={
            "name": {"type": "string"},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_node_issues": Tool(
        name="detect_node_issues",
        func=nodes.detect_node_issues,
        description="Detect node issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "drain_node": Tool(
        name="drain_node",
        func=nodes.drain_node,
        description="Drain node",
        category="action",
        parameters={
            "name": {"type": "string"},
            "ignore_daemonsets": {"type": "boolean", "default": True},
            "grace_period_seconds": {"type": "number", "default": 30},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_node": Tool(
        name="get_node",
        func=nodes.get_node,
        description="Get node",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_node_events": Tool(
        name="get_node_events",
        func=nodes.get_node_events,
        description="Get node events",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "uncordon_node": Tool(
        name="uncordon_node",
        func=nodes.uncordon_node,
        description="Uncordon node",
        category="action",
        parameters={
            "name": {"type": "string"},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "delete_pod": Tool(
        name="delete_pod",
        func=pods.delete_pod,
        description="Delete pod",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_pod_issues": Tool(
        name="detect_pod_issues",
        func=pods.detect_pod_issues,
        description="Detect pod issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_pod": Tool(
        name="get_pod",
        func=pods.get_pod,
        description="Get pod",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_pod_status_with_metrics": Tool(
        name="get_pod_status_with_metrics",
        func=pods.get_pod_status_with_metrics,
        description="Get pod status with metrics",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_pods": Tool(
        name="list_all_pods",
        func=pods.list_all_pods,
        description="List all pods",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_pods": Tool(
        name="list_pods",
        func=pods.list_pods,
        description="List pods",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "get_cluster_role": Tool(
        name="get_cluster_role",
        func=rbac.get_cluster_role,
        description="Get cluster role",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_cluster_role_binding": Tool(
        name="get_cluster_role_binding",
        func=rbac.get_cluster_role_binding,
        description="Get cluster role binding",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_role": Tool(
        name="get_role",
        func=rbac.get_role,
        description="Get role",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_role_binding": Tool(
        name="get_role_binding",
        func=rbac.get_role_binding,
        description="Get role binding",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_service_account": Tool(
        name="get_service_account",
        func=rbac.get_service_account,
        description="Get service account",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_service_accounts": Tool(
        name="list_all_service_accounts",
        func=rbac.list_all_service_accounts,
        description="List all service accounts",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "list_cluster_role_bindings": Tool(
        name="list_cluster_role_bindings",
        func=rbac.list_cluster_role_bindings,
        description="List cluster role bindings",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_cluster_roles": Tool(
        name="list_cluster_roles",
        func=rbac.list_cluster_roles,
        description="List cluster roles",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_role_bindings": Tool(
        name="list_role_bindings",
        func=rbac.list_role_bindings,
        description="List role bindings",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_roles": Tool(
        name="list_roles",
        func=rbac.list_roles,
        description="List roles",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_service_accounts": Tool(
        name="list_service_accounts",
        func=rbac.list_service_accounts,
        description="List service accounts",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "detect_quota_pressure": Tool(
        name="detect_quota_pressure",
        func=resource_quotas.detect_quota_pressure,
        description="Detect quota pressure",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_limit_range": Tool(
        name="get_limit_range",
        func=resource_quotas.get_limit_range,
        description="Get limit range",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_resource_quota": Tool(
        name="get_resource_quota",
        func=resource_quotas.get_resource_quota,
        description="Get resource quota",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_limit_ranges": Tool(
        name="list_limit_ranges",
        func=resource_quotas.list_limit_ranges,
        description="List limit ranges",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_resource_quotas": Tool(
        name="list_resource_quotas",
        func=resource_quotas.list_resource_quotas,
        description="List resource quotas",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "check_secret": Tool(
        name="check_secret",
        func=secrets.check_secret,
        description="Check secret",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "create_secret": Tool(
        name="create_secret",
        func=secrets.create_secret,
        description="Create secret",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "data": {"type": "string", "default": None},
            "secret_type": {"type": "string", "default": 'Opaque'},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_secret": Tool(
        name="delete_secret",
        func=secrets.delete_secret,
        description="Delete secret",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_secret_metadata": Tool(
        name="get_secret_metadata",
        func=secrets.get_secret_metadata,
        description="Get secret metadata",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_secret_values": Tool(
        name="get_secret_values",
        func=secrets.get_secret_values,
        description="Get secret values",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_secrets": Tool(
        name="list_secrets",
        func=secrets.list_secrets,
        description="List secrets",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "secret_exists": Tool(
        name="secret_exists",
        func=secrets.secret_exists,
        description="Secret exists",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "update_secret": Tool(
        name="update_secret",
        func=secrets.update_secret,
        description="Update secret",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "data": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "create_service": Tool(
        name="create_service",
        func=services.create_service,
        description="Create service",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "service_type": {"type": "string", "default": 'ClusterIP'},
            "selector": {"type": "string", "default": None},
            "ports": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_service": Tool(
        name="delete_service",
        func=services.delete_service,
        description="Delete service",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "get_service": Tool(
        name="get_service",
        func=services.get_service,
        description="Get service",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_services": Tool(
        name="list_all_services",
        func=services.list_all_services,
        description="List all services",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_services": Tool(
        name="list_services",
        func=services.list_services,
        description="List services",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "patch_service": Tool(
        name="patch_service",
        func=services.patch_service,
        description="Patch service",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "selector": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
            "ports": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_statefulset_issues": Tool(
        name="detect_statefulset_issues",
        func=statefulsets.detect_statefulset_issues,
        description="Detect statefulset issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_statefulset": Tool(
        name="get_statefulset",
        func=statefulsets.get_statefulset,
        description="Get statefulset",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "list_all_statefulsets": Tool(
        name="list_all_statefulsets",
        func=statefulsets.list_all_statefulsets,
        description="List all statefulsets",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "list_statefulsets": Tool(
        name="list_statefulsets",
        func=statefulsets.list_statefulsets,
        description="List statefulsets",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "restart_statefulset": Tool(
        name="restart_statefulset",
        func=statefulsets.restart_statefulset,
        description="Restart statefulset",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "scale_statefulset": Tool(
        name="scale_statefulset",
        func=statefulsets.scale_statefulset,
        description="Scale statefulset",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "replicas": {"type": "number", "default": 1},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "create_pvc": Tool(
        name="create_pvc",
        func=storage.create_pvc,
        description="Create pvc",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "size": {"type": "string", "default": '1Gi'},
            "access_modes": {"type": "string", "default": None},
            "storage_class": {"type": "string", "default": None},
            "labels": {"type": "string", "default": None},
        },
        permission_required="create",
        is_read_only=False,
    ),
    "delete_pvc": Tool(
        name="delete_pvc",
        func=storage.delete_pvc,
        description="Delete pvc",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        permission_required="modify",
        is_read_only=False,
    ),
    "detect_pvc_issues": Tool(
        name="detect_pvc_issues",
        func=storage.detect_pvc_issues,
        description="Detect pvc issues",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_pv": Tool(
        name="get_pv",
        func=storage.get_pv,
        description="Get pv",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "get_pvc": Tool(
        name="get_pvc",
        func=storage.get_pvc,
        description="Get pvc",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
        },
        is_read_only=True,
    ),
    "get_storage_class": Tool(
        name="get_storage_class",
        func=storage.get_storage_class,
        description="Get storage class",
        category="diagnostics",
        parameters={
            "name": {"type": "string"},
        },
        is_read_only=True,
    ),
    "list_pvcs": Tool(
        name="list_pvcs",
        func=storage.list_pvcs,
        description="List pvcs",
        category="diagnostics",
        parameters={
            "namespace": {"type": "string", "default": 'default'},
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_pvs": Tool(
        name="list_pvs",
        func=storage.list_pvs,
        description="List pvs",
        category="diagnostics",
        parameters={
            "label_selector": {"type": "string", "default": None},
        },
        is_read_only=True,
    ),
    "list_storage_classes": Tool(
        name="list_storage_classes",
        func=storage.list_storage_classes,
        description="List storage classes",
        category="diagnostics",
        parameters={},
        is_read_only=True,
    ),
    "patch_pvc": Tool(
        name="patch_pvc",
        func=storage.patch_pvc,
        description="Patch pvc",
        category="action",
        parameters={
            "name": {"type": "string"},
            "namespace": {"type": "string", "default": 'default'},
            "labels": {"type": "string", "default": None},
        },
        permission_required="modify",
        is_read_only=False,
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


async def execute_tool(tool_name: str, **kwargs) -> DiagnosticResult:
    """Execute a tool by name.

    Args:
        tool_name: Tool name
        **kwargs: Arguments for the tool

    Returns:
        DiagnosticResult with outcome

    Raises:
        ValueError: If tool not found
    """
    tool = get_tool_by_name(tool_name)
    if not tool:
        raise ValueError(f"Tool '{tool_name}' not found in registry")

    return await tool.execute(**kwargs)


def get_all_tools() -> List[Tool]:
    """Get all available tools."""
    return list(MONITORING_TOOL_REGISTRY.values())


def get_tool_definitions() -> List[ToolDefinition]:
    """Get all tool definitions for LLM consumption."""
    return [tool.to_definition() for tool in get_all_tools()]
