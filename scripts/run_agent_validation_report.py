"""Run integration tests and print a live agent validation report.

This script does two things in order:
1) Runs selected pytest suites so you can see full errors.
2) Feeds recent real warning events to the monitoring graph and prints:
   - agent response summary
   - root cause
   - suggested fixes/actions
   - tools called

Usage examples:
  .venv/Scripts/python.exe scripts/run_agent_validation_report.py --run-tests
  .venv/Scripts/python.exe scripts/run_agent_validation_report.py --events 5
  .venv/Scripts/python.exe scripts/run_agent_validation_report.py --run-tests --events 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.events import list_warning_events
from app.agent.monitoring_graph import build_monitoring_graph
from app.agent.schemas import EnrichedEventInput, ResourceType, SeverityLevel


def _map_resource_type(kind: str | None) -> ResourceType:
    mapping = {
        "Pod": ResourceType.POD,
        "Deployment": ResourceType.DEPLOYMENT,
        "StatefulSet": ResourceType.STATEFULSET,
        "DaemonSet": ResourceType.DAEMONSET,
        "Job": ResourceType.JOB,
        "CronJob": ResourceType.CRONJOB,
        "Service": ResourceType.SERVICE,
        "Ingress": ResourceType.INGRESS,
        "ConfigMap": ResourceType.CONFIGMAP,
        "Secret": ResourceType.SECRET,
        "Node": ResourceType.NODE,
        "Namespace": ResourceType.NAMESPACE,
    }
    return mapping.get(kind or "", ResourceType.POD)


def _run_pytest(cmd: list[str], label: str) -> int:
    print("\n" + "=" * 80)
    print(f"TEST RUN: {label}")
    print("COMMAND:", " ".join(cmd))
    print("=" * 80)
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    print(f"\nRESULT [{label}] exit_code={result.returncode}")
    return result.returncode


def _flatten_suggestions(suggested_actions: Iterable) -> list[str]:
    lines: list[str] = []
    for idx, action in enumerate(suggested_actions, start=1):
        if hasattr(action, "description"):
            atype = getattr(action, "action_type", "unknown")
            desc = getattr(action, "description", "")
            target = getattr(action, "target_resource", "")
            risk = getattr(action, "estimated_risk", "")
            lines.append(f"{idx}. [{atype}] {desc} (target={target}, risk={risk})")
        elif isinstance(action, dict):
            atype = action.get("action_type", "unknown")
            desc = action.get("description", "")
            target = action.get("target_resource", "")
            risk = action.get("estimated_risk", "")
            lines.append(f"{idx}. [{atype}] {desc} (target={target}, risk={risk})")
        else:
            lines.append(f"{idx}. {action}")
    return lines


async def _run_agent_report(events_to_run: int) -> int:
    print("\n" + "=" * 80)
    print("AGENT REPORT: LIVE WARNING EVENTS")
    print("=" * 80)

    warnings = list_warning_events(limit=max(events_to_run * 3, 20))
    if not warnings:
        print("No warning events found. Create failing workloads first.")
        return 1

    graph = build_monitoring_graph()
    selected = warnings[:events_to_run]

    pass_count = 0
    fail_count = 0

    for i, ev in enumerate(selected, start=1):
        involved = ev.get("involved_object", {})
        resource_name = involved.get("name") or ev.get("name") or "unknown"
        namespace = involved.get("namespace") or ev.get("namespace") or "default"
        reason = ev.get("reason") or "Unknown"
        message = ev.get("message") or ""
        kind = involved.get("kind") or "Pod"

        event = EnrichedEventInput(
            resource_type=_map_resource_type(kind),
            resource_name=resource_name,
            namespace=namespace,
            reason=reason,
            severity=SeverityLevel.WARNING,
            teams=["platform-team"],
            timestamp=datetime.now(timezone.utc),
            dedup_fingerprint=f"validation/{namespace}/{resource_name}/{reason}/{i}",
            raw_count=int(ev.get("count") or 1),
            message=message,
            additional_context={"source": "run_agent_validation_report"},
        )

        print("\n" + "-" * 80)
        print(f"CASE {i}: {kind}/{resource_name} ns={namespace} reason={reason}")
        print("-" * 80)

        try:
            out = await graph.ainvoke({"event": event})
            incident = out.get("incident_record")
            if incident is None:
                print("FAIL: incident_record missing")
                fail_count += 1
                continue

            tools = getattr(incident, "tools_called", []) or []
            summary = getattr(incident, "summary", "") or ""
            detailed = getattr(incident, "detailed_summary", "") or ""
            log_snapshot = getattr(incident, "log_snapshot", "") or ""
            root_cause = ""
            rca = getattr(incident, "root_cause_analysis", None)
            if rca is not None:
                root_cause = getattr(rca, "root_cause", "") or ""
            actions = _flatten_suggestions(getattr(incident, "suggested_actions", []) or [])

            print("AGENT RESPONSE:")
            print(summary if summary else "(empty summary)")

            print("\nROOT CAUSE:")
            print(root_cause if root_cause else "(not provided)")

            print("\nSUGGESTED FIXES:")
            if actions:
                for line in actions:
                    print(line)
            else:
                print("(no suggested actions)")

            print("\nTOOLS CALLED:")
            print(", ".join(tools) if tools else "(none)")

            if detailed:
                print("\nDETAILED SUMMARY:")
                print(detailed)

            if log_snapshot:
                print("\nLOG SNAPSHOT:")
                print(log_snapshot)

            pass_count += 1
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")
            fail_count += 1

    print("\n" + "=" * 80)
    print(f"AGENT REPORT RESULT: pass={pass_count} fail={fail_count} total={len(selected)}")
    print("=" * 80)
    return 0 if fail_count == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tests and print live agent response report.")
    parser.add_argument("--run-tests", action="store_true", help="Run monitor and tools test suites first.")
    parser.add_argument("--events", type=int, default=5, help="Number of warning events to feed to the agent.")
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "z-ai/glm4.7"),
        help="NVIDIA/OpenAI-compatible model id (default: z-ai/glm4.7).",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        help="NVIDIA OpenAI-compatible chat completions URL.",
    )
    args = parser.parse_args()

    # Enforce real LLM usage for this report.
    if not os.getenv("NVIDIA_API_KEY") and not os.getenv("LLM_API_KEY"):
        print("ERROR: Missing NVIDIA_API_KEY (or LLM_API_KEY).")
        print("Set a real API key in your environment or .env file before running this script.")
        return 3

    os.environ["LLM_PROVIDER"] = "nvidia"
    os.environ["LLM_MODEL"] = args.model
    os.environ["NVIDIA_API_BASE_URL"] = args.base_url

    overall_code = 0

    if args.run_tests:
        py = str(Path(sys.executable))
        monitor_cmd = [py, "-m", "pytest", "tests/test_monitor_integration.py", "-v", "--tb=long", "-s"]
        tools_cmd = [py, "-m", "pytest", "tests/test_tools.py", "-m", "integration or slow", "-v", "--tb=long", "-s"]

        code1 = _run_pytest(monitor_cmd, "monitor_integration")
        code2 = _run_pytest(tools_cmd, "tools_integration_slow")
        overall_code = max(overall_code, code1, code2)

    code3 = asyncio.run(_run_agent_report(max(args.events, 1)))
    overall_code = max(overall_code, code3)
    return overall_code


if __name__ == "__main__":
    raise SystemExit(main())
