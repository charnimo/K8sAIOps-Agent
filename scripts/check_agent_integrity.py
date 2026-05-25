"""Integrity check for the monitoring agent using the real LLM and real tools."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.agent.schemas import EnrichedEventInput, ResourceType, SeverityLevel
import app.agent.monitoring_graph as mg


async def run_check() -> dict[str, Any]:
    """Run the monitoring graph end-to-end with live tools and the real LLM."""

    state = {
        "event": EnrichedEventInput(
            resource_type=ResourceType.POD,
            resource_name="demo-pod",
            namespace="default",
            reason="CrashLoopBackOff",
            severity=SeverityLevel.CRITICAL,
            teams=["platform-team"],
            timestamp=datetime.now(timezone.utc),
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
    if not os.getenv("NVIDIA_API_KEY"):
        raise SystemExit("NVIDIA_API_KEY is required for this integrity check")

    result = asyncio.run(run_check())
    print(json.dumps(result, indent=2))
