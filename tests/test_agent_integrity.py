"""Integrity tests for the app.agent layer.

These checks help ensure the agent package stays as orchestration/wrappers
around the existing monitor.py and Tools/ implementation rather than
re-implementing the same public functions.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.agent import monitoring_graph as agent_graph
from app.agent import tools as agent_tools
from Tools import deployments as tools_deployments
from Tools import diagnostics as tools_diagnostics
from Tools import pods as tools_pods


def _public_callables(module):
    return {
        name
        for name, value in inspect.getmembers(module)
        if (inspect.isfunction(value) or inspect.isclass(value)) and not name.startswith("_")
    }


def test_agent_graph_does_not_duplicate_monitor_public_api():
    """The agent graph should not recreate monitor.py's public classes/functions."""
    monitor_source = Path(__file__).resolve().parents[1] / "monitoring" / "monitor.py"
    monitor_public = {
        node.name
        for node in ast.walk(ast.parse(monitor_source.read_text(encoding="utf-8")))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }
    agent_public = _public_callables(agent_graph)

    # The agent graph should define its own orchestration nodes, not reuse
    # the monitor module's public API surface.
    overlap = monitor_public & agent_public
    assert overlap == set(), f"Unexpected public name overlap: {sorted(overlap)}"


def test_agent_tool_registry_uses_existing_tools_functions():
    """Agent tool wrappers should reference existing Tools functions, not placeholders."""
    registry = agent_tools.MONITORING_TOOL_REGISTRY

    expected_co_names = {
        "get_pod_logs": "get_pod_logs",
        "get_pod_events": "get_pod_events",
        "get_pod_status": "get_pod_status",
        "get_pod_metrics": "get_pod_metrics",
        "get_deployment_info": "get_deployment",
        "list_nodes": "list_nodes",
        "describe_pod": "diagnose_pod",
        "describe_deployment": "diagnose_deployment",
    }

    for tool_name, expected_name in expected_co_names.items():
        assert tool_name in expected_co_names
        assert tool_name in registry
        wrapper = registry[tool_name]
        co_names = set(wrapper.func.__code__.co_names)
        assert expected_name in co_names


def test_existing_tools_are_available_from_canonical_package():
    """Sanity check that the canonical Tools package exposes the functions we wrap."""
    assert hasattr(tools_pods, "get_pod_logs")
    assert hasattr(tools_pods, "get_pod_events")
    assert hasattr(tools_pods, "get_pod_status")
    assert hasattr(tools_pods, "describe_pod")
    assert hasattr(tools_deployments, "get_deployment")
    assert hasattr(tools_diagnostics, "diagnose_pod")
    assert hasattr(tools_diagnostics, "diagnose_deployment")
