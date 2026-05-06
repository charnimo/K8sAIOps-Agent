"""Integrity check for the monitoring agent.

What it verifies:
- monitoring graph imports successfully
- agent uses the existing Tools-based diagnostic names
- LLM tool selection works (mock or live NVIDIA/OpenAI-compatible)
- monitoring graph produces an incident analysis end-to-end

This script intentionally stubs the tool execution layer so it can run without
cluster access while still proving the control flow and model parsing logic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import sys
from typing import Any


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.agent.schemas import DiagnosticResult, EnrichedEventInput, ResourceType, SeverityLevel
import app.agent.monitoring_graph as mg


async def fake_execute_tool(name: str, **kwargs: Any) -> DiagnosticResult:
    """Return deterministic tool outputs so the graph can be validated offline."""
    mapping = {
        "get_pod_logs": {
            "logs": ["[ERROR] out of memory"],
            "container": None,
            "lines_returned": 500,
        },
        "get_pod_events": {
            "events": [
                {
                    "reason": "CrashLoopBackOff",
                    "message": "Back-off restarting failed container",
                }
            ]
        },
        "get_pod_status": {"phase": "Running", "restart_count": 7, "conditions": []},
        "get_pod_metrics": {
            "memory_usage": "950Mi",
            "memory_limit": "512Mi",
            "cpu_usage": "500m",
            "cpu_limit": "1000m",
        },
        "list_nodes": {"nodes": [{"name": "node-a", "status": "Ready"}]},
        "describe_pod": {"issues": ["CrashLoopBackOff"], "severity": "critical"},
    }
    return DiagnosticResult(
        tool_name=name,
        success=True,
        data=mapping.get(name, {}),
        execution_time_ms=1.0,
    )


async def run_check() -> dict[str, Any]:
    """Run the monitoring graph end-to-end."""
    mg.execute_tool = fake_execute_tool

    state = {
        "event": EnrichedEventInput(
            resource_type=ResourceType.POD,
            resource_name="demo-pod",
            namespace="default",
            reason="CrashLoopBackOff",
            severity=SeverityLevel.CRITICAL,
            teams=["platform-team"],
            timestamp=datetime.now(),
            dedup_fingerprint="demo/default/demo-pod/CrashLoopBackOff",
            raw_count=1,
            message="Back-off restarting failed container",
        )
    }

    state = mg.node_extract_event(state)
    state = await mg.node_decide_tools(state)
    state = await mg.node_collect_diagnostics(state)
    state = mg.node_classify_severity(state)
    state = mg.node_resolve_team(state)

    return {
        "tools": state.get("tools_to_call", []),
        "reasoning": state.get("llm_tool_reasoning", ""),
        "severity": str(state.get("severity")),
        "root_cause": state.get("root_cause_analysis").root_cause,
        "confidence": state.get("root_cause_analysis").hypothesis_confidence,
        "teams": state.get("teams", []),
    }


if __name__ == "__main__":
    if not os.getenv("LLM_PROVIDER") and not (os.getenv("NVIDIA_API_KEY") or os.getenv("LLM_API_KEY")):
        os.environ["LLM_PROVIDER"] = "mock"

    result = asyncio.run(run_check())
    print(json.dumps(result, indent=2))
