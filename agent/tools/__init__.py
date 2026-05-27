"""
agent/tools/__init__.py

Public API for the agent tool layer.

Usage in LangGraph:
    from agent.tools import get_tool_group, ToolGroup

    # Give the agent only what it needs for the current task
    tools = get_tool_group(ToolGroup.READ, token=user_token)
    tools += get_tool_group(ToolGroup.OBSERVABILITY, token=user_token)

Tool groups:
    READ          — list/inspect any k8s resource. No side effects.
    OBSERVABILITY — metrics, logs, events, pressure analysis.
    DIAGNOSTIC    — active diagnosis, issue classification, health checks.
    ACTION        — all mutations. Load only when user requests a change.
    CLUSTER       — audit logs, platform health.

Design rules:
    - Never load ACTION tools unless the user has explicitly requested
      a mutation. Read + Diagnostic + Observability cover all inspection.
    - Groups can be combined freely. A triage session might load
      READ + OBSERVABILITY + DIAGNOSTIC together.
    - Each build_* call creates fresh tool closures bound to the given
      token. Never share tool instances across agent runs.
"""

from __future__ import annotations

from enum import Enum

from .action_tools import build_action_tools
from .cluster_tools import build_cluster_tools
from .diagnostic_tools import build_diagnostic_tools
from .docs_tools import build_docs_tools
from .observability_tools import build_observability_tools
from .read_tools import build_read_tools


class ToolGroup(str, Enum):
    READ = "read"
    OBSERVABILITY = "observability"
    DIAGNOSTIC = "diagnostic"
    ACTION = "action"
    CLUSTER = "cluster"
    DOCS = "docs"


_BUILDERS = {
    ToolGroup.READ: build_read_tools,
    ToolGroup.OBSERVABILITY: build_observability_tools,
    ToolGroup.DIAGNOSTIC: build_diagnostic_tools,
    ToolGroup.ACTION: build_action_tools,
    ToolGroup.CLUSTER: build_cluster_tools,
    ToolGroup.DOCS: build_docs_tools,
}


def get_tool_group(group: ToolGroup, token: str) -> list:
    """Return a list of LangChain tools for the given group, bound to the token."""
    builder = _BUILDERS.get(group)
    if builder is None:
        raise ValueError(f"Unknown tool group: {group}")
    return builder(token)


def get_tools_for_task(task: str, token: str, include_docs: bool = True) -> list:
    """
    Return the recommended tool set for a given task type.

    Convenience helper for LangGraph node construction. The agent
    implementation can call this instead of manually composing groups.

    task options:
        Documentation retrieval is included for inspect, triage, act, and full
        unless include_docs is False.
        'inspect'     — READ only. User wants to list or describe resources.
        'triage'      — READ + OBSERVABILITY + DIAGNOSTIC. User reports a problem.
        'act'         — READ + OBSERVABILITY + DIAGNOSTIC + ACTION. User wants a change.
        'audit'       — CLUSTER only. User wants to see what happened recently.
        'full'        — All groups. God-mode sessions or open-ended investigation.
    """
    task_map: dict[str, list[ToolGroup]] = {
        "inspect": [ToolGroup.READ, ToolGroup.DOCS],
        "triage":  [ToolGroup.READ, ToolGroup.OBSERVABILITY, ToolGroup.DIAGNOSTIC, ToolGroup.DOCS],
        "act":     [ToolGroup.READ, ToolGroup.OBSERVABILITY, ToolGroup.DIAGNOSTIC, ToolGroup.DOCS, ToolGroup.ACTION],
        "audit":   [ToolGroup.CLUSTER],
        "full":    list(ToolGroup),
    }
    groups = task_map.get(task)
    if groups is None:
        raise ValueError(f"Unknown task type: '{task}'. Choose from: {list(task_map)}")

    tools = []
    for group in groups:
        if group == ToolGroup.DOCS and not include_docs:
            continue
        tools.extend(get_tool_group(group, token))
    return tools


__all__ = [
    "ToolGroup",
    "get_tool_group",
    "get_tools_for_task",
    "build_read_tools",
    "build_observability_tools",
    "build_diagnostic_tools",
    "build_action_tools",
    "build_cluster_tools",
    "build_docs_tools",
]
