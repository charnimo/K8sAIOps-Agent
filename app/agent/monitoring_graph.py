"""Monitoring graph: Automated incident detection and diagnostics.

LangGraph DAG that:
1. Extracts and normalizes Kubernetes events
2. Uses LLM to decide which diagnostic tools to call
3. Collects diagnostics
4. Classifies severity
5. Resolves recipient ownership
6. Persists incident record
7. Notifies interested recipients
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph
from pydantic import ValidationError

from app.agent.schemas import (
    MonitoringGraphState,
    EnrichedEventInput,
    DiagnosticResult,
    IncidentRecord,
    IncidentStatus,
    SeverityLevel,
    RootCauseAnalysis,
    SuggestedAction,
    RemediationStep,
    ResourceType,
)
from app.agent.recipients import resolve_concerned_users_for_event
from app.agent.tools import (
    execute_tool,
    get_tool_definitions,
)
from app.agent.config import get_llm_client
from app.database.database import SessionLocal
from app.database.models import IncidentRecord as IncidentRecordModel

logger = logging.getLogger(__name__)

ALLOWED_BASIC_ACTION_TOOLS = [
    "restart_pod",
    "scale_deployment",
    "rollout_restart",
    "patch_resource_limits",
]


# ============================================================================
# NODE 1: EXTRACT EVENT
# ============================================================================


def node_extract_event(state: MonitoringGraphState) -> MonitoringGraphState:
    """Extract and validate event from input.

    This is a simple passthrough that validates the input event.
    In practice, this would normalize raw K8s event objects.

    Args:
        state: Graph state with event

    Returns:
        Updated state with validation
    """
    try:
        event = state["event"]

        # Accept several incoming shapes:
        # - dict compatible with EnrichedEventInput
        # - EnrichedEventInput pydantic model
        # - monitoring.monitor.EnrichedEvent dataclass (or similar object)
        if isinstance(event, dict):
            event = EnrichedEventInput(**event)
        elif isinstance(event, EnrichedEventInput):
            pass
        else:
            # Try to coerce objects produced by `monitoring.monitor.EnrichedEvent`.
            # These objects expose attributes such as resource_kind, resource_name,
            # namespace, reason, severity (enum), timestamp (ISO string), etc.
            try:
                resource_kind = getattr(event, "resource_kind", None) or getattr(event, "resource_type", None)
                try:
                    resource_type = ResourceType(resource_kind) if resource_kind else ResourceType.POD
                except Exception:
                    resource_type = ResourceType.POD

                resource_name = getattr(event, "resource_name", getattr(event, "resource", "unknown"))
                namespace = getattr(event, "namespace", "default")
                reason = getattr(event, "reason", "Unknown")

                sev = getattr(event, "severity", None)
                if hasattr(sev, "value"):
                    sev_val = sev.value
                else:
                    sev_val = str(sev) if sev is not None else "WARNING"
                try:
                    severity = SeverityLevel(sev_val)
                except Exception:
                    severity = SeverityLevel.WARNING

                ts = getattr(event, "timestamp", None)
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except Exception:
                        ts = datetime.now()
                elif ts is None:
                    ts = datetime.now()

                dedup = getattr(event, "event_id", None) or getattr(event, "dedup_fingerprint", None)
                if not dedup:
                    dedup = f"{namespace}/{resource_name}/{reason}"

                raw_count = int(getattr(event, "raw_count", 1) or 1)
                message = getattr(event, "message", "")
                additional_context = getattr(event, "additional_context", {}) or {}

                event = EnrichedEventInput(
                    resource_type=resource_type,
                    resource_name=resource_name,
                    namespace=namespace,
                    reason=reason,
                    severity=severity,
                    timestamp=ts,
                    dedup_fingerprint=dedup,
                    raw_count=raw_count,
                    message=message,
                    additional_context=additional_context,
                )
            except Exception as e:
                raise ValueError(
                    f"Invalid event type: {type(event)}. Expected dict or EnrichedEventInput"
                ) from e

        state["event"] = event
        state["execution_start_time"] = datetime.now()

        logger.info(
            f"Extracted event: {event.resource_type} {event.resource_name} in {event.namespace} ({event.reason})"
        )

        return state

    except ValidationError as e:
        state["errors"] = [f"Event validation failed: {str(e)}"]
        logger.error(f"Event validation error: {e}")
        return state
    except Exception as e:
        state["errors"] = [f"Event extraction failed: {str(e)}"]
        logger.error(f"Event extraction error: {e}", exc_info=True)
        return state


# ============================================================================
# NODE 2: DECIDE WHICH TOOLS TO CALL (LLM)
# ============================================================================


async def node_decide_tools(state: MonitoringGraphState) -> MonitoringGraphState:
    """Use LLM to decide which diagnostic tools to call.

    This is the agentic part: LLM analyzes the event and selects appropriate tools.

    Args:
        state: Graph state with event

    Returns:
        Updated state with tools_to_call and reasoning
    """
    try:
        event = state["event"]

        # Build LLM prompt
        tool_definitions = get_tool_definitions()
        tool_names = {tool.name for tool in tool_definitions}
        action_tool_names = [name for name in ALLOWED_BASIC_ACTION_TOOLS if name in tool_names]
        # Include category and read-only flag to help the LLM distinguish actions
        tools_description = "\n".join(
            [f"- {t.name} (category={t.category}, read_only={t.is_read_only}): {t.description}" for t in tool_definitions]
        )

        prompt = f"""
You are a Kubernetes diagnostics expert. An incident has occurred in the cluster.

EVENT DETAILS:
- Namespace: {event.namespace}
- Reason: {event.reason}
- Severity: {event.severity}
- Message: {event.message}
- Additional Context: {json.dumps(event.additional_context, indent=2)}

AVAILABLE DIAGNOSTIC TOOLS:
{tools_description}
Note: Some tools are actions (will mutate cluster state) and require explicit approval.
Return two lists:
1) `tools`: read-only diagnostic/query tools the agent should execute now.
2) `suggested_actions`: action/mutation tools you would recommend (do not execute without approval).
Also return `remediation_plan` and `evidence_map`.

Allowed action tools:
{", ".join(action_tool_names)}

Rules for fixes:
- Keep fixes basic and practical.
- Use only the allowed action tool names above.
- Prefer 1-2 small-scope actions over long or speculative plans.
- Do not invent new action names, resource kinds, or remediation steps.

Prefer read-only tools for initial diagnostics. If the incident severity is critical, you may include higher-impact diagnostics (e.g., `describe_deployment`) in `tools`.

Respond in this JSON format:
{{
    "tools": ["tool_name1", "tool_name2"],
    "suggested_actions": ["action_tool_name1"],
    "remediation_plan": [
        {{"step_number": 1, "action_type": "action_tool_name1", "description": "...", "target_resource": "...", "why": "...", "evidence": ["..."], "estimated_risk": "LOW"}}
    ],
    "evidence_map": {{"action_tool_name1": ["evidence snippet"]}},
    "reasoning": "Why you selected these tools"
}}
"""

        llm_client = get_llm_client()

        logger.info(
            f"Calling LLM to select tools for {event.resource_type} {event.resource_name}"
        )

        response = await llm_client.ainvoke(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Kubernetes diagnostics planner. "
                        "Return only JSON with keys: tools, suggested_actions, remediation_plan, evidence_map, and reasoning. "
                        "Do not invent facts and do not omit evidence references when available."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
        )
        llm_response_text = llm_client.extract_text(response)
        logger.debug("LLM tool-selection response text: %s", llm_response_text)
        logger.debug("LLM raw response object: %s", response)
        if not llm_response_text:
            raise ValueError("LLM returned an empty tool-selection response")

        response_model = str(response.get("model") or response.get("id") or llm_client.model).strip()
        response_source = "live_nvidia_api"

        response_json = _extract_json_payload(llm_response_text)
        tools_to_call = response_json.get("tools", [])
        suggested_actions = response_json.get("suggested_actions", [])
        remediation_plan = response_json.get("remediation_plan", [])
        evidence_map = response_json.get("evidence_map", {})
        llm_reasoning = response_json.get("reasoning", "")

        # Only keep known tools.
        raw_tools = [tool for tool in tools_to_call if tool in tool_names]
        raw_suggested_actions = [tool for tool in suggested_actions if tool in tool_names]

        if not raw_tools:
            raise ValueError("LLM did not return any known diagnostic tools")

        # Store the LLM output as-is after verifying the tool names exist in the registry.
        state["tools_to_call"] = raw_tools
        state["suggested_action_tools"] = raw_suggested_actions
        state["remediation_plan"] = remediation_plan
        state["evidence_map"] = _normalize_evidence_map(evidence_map)
        state["llm_tool_reasoning"] = llm_reasoning
        state["llm_provider"] = "nvidia"
        state["llm_model"] = llm_client.model
        state["llm_response_model"] = response_model
        state["llm_response_source"] = response_source

        logger.info(
            f"LLM selected tools: {tools_to_call}, suggested_actions: {suggested_actions}. Reasoning: {llm_reasoning}"
        )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Tool selection failed: {str(e)}"
        ]
        logger.error(f"Tool selection error: {e}", exc_info=True)
        raise


# ============================================================================
# NODE 3: COLLECT DIAGNOSTICS
# ============================================================================


async def node_collect_diagnostics(
    state: MonitoringGraphState,
) -> MonitoringGraphState:
    """Execute selected tools to collect diagnostics.

    Runs tools in parallel for efficiency.

    Args:
        state: Graph state with tools_to_call

    Returns:
        Updated state with collected_diagnostics
    """
    try:
        event = state["event"]
        tools_to_call = state.get("tools_to_call", [])
        # Enforce policy: never execute action/mutation tools from the registry.
        tool_defs = get_tool_definitions()
        tools_to_call = [t for t in tools_to_call if _is_tool_read_only(t, tool_defs)]
        state["tools_to_call_executed"] = tools_to_call

        if not tools_to_call:
            logger.warning("No tools to call for diagnostics")
            state["collected_diagnostics"] = {}
            return state

        # Build tool execution parameters based on resource type
        tool_params = _build_tool_parameters(event, tools_to_call)

        logger.info(f"Executing {len(tools_to_call)} diagnostic tools...")

        # Execute tools in parallel
        tasks = []
        for tool_name in tools_to_call:
            if tool_name in tool_params:
                params = tool_params[tool_name]
                tasks.append(execute_tool(tool_name, **params))
            else:
                logger.warning(f"No parameters available for tool: {tool_name}")

        # Wait for all tools to complete
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # Aggregate results
        collected = {}
        for result in results:
            if isinstance(result, DiagnosticResult):
                collected[result.tool_name] = result
            else:
                logger.warning(f"Unexpected result type: {type(result)}")

        state["collected_diagnostics"] = collected

        # Log summary
        successful = sum(1 for r in results if isinstance(r, DiagnosticResult) and r.success)
        logger.info(f"Tool execution complete: {successful}/{len(tools_to_call)} successful")

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Diagnostic collection failed: {str(e)}"
        ]
        logger.error(f"Diagnostic collection error: {e}", exc_info=True)
        return state


# ============================================================================
# NODE 4: CLASSIFY SEVERITY
# ============================================================================


async def node_classify_severity(state: MonitoringGraphState) -> MonitoringGraphState:
    """Use the LLM to classify severity and summarize the incident."""
    try:
        event = state["event"]
        diagnostics = state.get("collected_diagnostics", {})
        tool_definitions = get_tool_definitions()
        allowed_action_tools = sorted({tool.name for tool in tool_definitions if not tool.is_read_only})

        analysis = await _run_llm_incident_analysis(event, diagnostics)
        severity_value = str(analysis.get("severity", "")).strip()
        if severity_value not in {"INFO", "WARNING", "CRITICAL"}:
            raise ValueError(f"Invalid severity from LLM: {severity_value!r}")

        root_cause = _normalize_root_cause_analysis(analysis.get("root_cause_analysis"))

        suggested_actions_raw = analysis.get("suggested_actions", [])
        remediation_plan_raw = analysis.get("remediation_plan", [])
        evidence_map_raw = analysis.get("evidence_map", {})

        if not isinstance(evidence_map_raw, dict):
            raise ValueError("LLM did not return a valid evidence_map object")

        state["severity"] = SeverityLevel(severity_value)
        state["root_cause_analysis"] = root_cause
        state["summary"] = str(analysis.get("summary", "")).strip()
        state["detailed_summary"] = str(analysis.get("detailed_summary", "")).strip()
        state["suggested_actions"] = [
            SuggestedAction(
                action_type=str(item.get("action_type") or item.get("action") or "").strip(),
                description=str(item.get("description") or item.get("summary") or "").strip(),
                target_resource=str(item.get("target_resource") or item.get("target") or "").strip(),
                priority=_coerce_int(item.get("priority"), idx),
                estimated_risk=str(item.get("estimated_risk") or "LOW").strip().upper(),
                rationale=str(item.get("rationale") or item.get("why") or "").strip() or None,
                evidence=_coerce_list(item.get("evidence")),
            )
            for idx, item in enumerate(suggested_actions_raw, start=1)
            if isinstance(item, dict)
            and str(item.get("action_type") or item.get("action") or "").strip() in allowed_action_tools
        ]
        state["remediation_plan"] = [
            step
            for idx, item in enumerate(remediation_plan_raw, start=1)
            if (step := _normalize_remediation_item(item, idx, allowed_action_tools)) is not None
        ]
        state["evidence_map"] = _normalize_evidence_map(evidence_map_raw)

        logger.info(
            f"LLM incident analysis complete: severity={severity_value}, root cause={state['root_cause_analysis'].root_cause}"
        )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Severity classification failed: {str(e)}"
        ]
        logger.error(f"Severity classification error: {e}", exc_info=True)
        raise


# ============================================================================
# NODE 5: RESOLVE RECIPIENT
# ============================================================================


def node_resolve_recipient(state: MonitoringGraphState) -> MonitoringGraphState:
    """Resolve the best recipient using the namespace permission map."""
    try:
        event = state["event"]
        resolution = resolve_concerned_users_for_event(
            namespace=event.namespace,
            resource_type=event.resource_type,
            additional_context=event.additional_context,
        )

        state["concerned_users"] = resolution.get("concerned_users", [])
        state["concerned_person"] = resolution.get("primary_concerned_user")
        state["owner_hints"] = resolution.get("owner_hints", [])

        if state.get("concerned_person"):
            person = state["concerned_person"]
            logger.info(
                "Resolved recipient for %s/%s -> %s (%s)",
                event.namespace,
                event.resource_name,
                person.get("display_name"),
                person.get("email"),
            )
        else:
            logger.info(
                "No specific recipient resolved for %s/%s; continuing with fallback routing",
                event.namespace,
                event.resource_name,
            )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Recipient resolution failed: {str(e)}"
        ]
        logger.error(f"Recipient resolution error: {e}", exc_info=True)
        state["concerned_users"] = []
        state["concerned_person"] = None
        state["owner_hints"] = []
        return state


# ============================================================================
# NODE 6: PERSIST INCIDENT RECORD
# ============================================================================


async def node_persist_incident(
    state: MonitoringGraphState,
) -> MonitoringGraphState:
    """Create and persist incident record to database."""
    try:
        event = state["event"]
        diagnostics = state.get("collected_diagnostics", {})
        severity = state.get("severity", event.severity)
        root_cause = state.get("root_cause_analysis")
        concerned_person = state.get("concerned_person")
        concerned_users = state.get("concerned_users", [])
        owner_hints = state.get("owner_hints", [])
        log_snapshot = _build_log_snapshot(diagnostics)
        summary = str(state.get("summary", "")).strip()
        detailed_summary = str(state.get("detailed_summary", "")).strip()
        remediation_plan = state.get("remediation_plan", [])
        evidence_map = state.get("evidence_map", {})
        suggested_actions = state.get("suggested_actions", [])

        if not summary:
            raise ValueError("Missing LLM summary for incident record")
        if not detailed_summary:
            raise ValueError("Missing LLM detailed summary for incident record")
        if not isinstance(root_cause, RootCauseAnalysis):
            raise ValueError("Missing LLM root cause analysis for incident record")
        if not remediation_plan:
            raise ValueError("Missing LLM remediation plan for incident record")

        # Build incident record
        incident = IncidentRecord(
            incident_id=f"inc_{datetime.now().timestamp():.0f}",
            trace_id=f"trace_{event.namespace}_{event.resource_name}_{datetime.now().timestamp():.0f}",
            conversation_id=None,  # Set when linked to chat
            resource_type=event.resource_type,
            resource_name=event.resource_name,
            namespace=event.namespace,
            reason=event.reason,
            severity=severity,
            summary=summary,
            detailed_summary=detailed_summary,
            log_snapshot=log_snapshot,
            collected_diagnostics={
                name: result.dict() for name, result in diagnostics.items()
            },
            tools_called=list(diagnostics.keys()),
            llm_reasoning=state.get("llm_tool_reasoning"),
            llm_provider=state.get("llm_provider"),
            llm_model=state.get("llm_model"),
            llm_response_model=state.get("llm_response_model"),
            llm_response_source=state.get("llm_response_source"),
            root_cause_analysis=root_cause,
            suggested_actions=suggested_actions,
            remediation_plan=remediation_plan,
            evidence_map=evidence_map,
            concerned_person=concerned_person,
            concerned_users=concerned_users,
            owner_hints=owner_hints,
            status=IncidentStatus.OPEN,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Persist incident record to the database
        session = SessionLocal()
        try:
            # Filter the pydantic model dict to the DB model's columns to avoid
            # passing unexpected/extra fields (e.g., llm_model metadata).
            incident_payload = incident.dict()
            allowed_cols = {c.name for c in IncidentRecordModel.__table__.columns}
            filtered = {k: v for k, v in incident_payload.items() if k in allowed_cols}
            session.add(IncidentRecordModel(**filtered))
            session.commit()
        finally:
            session.close()

        state["incident_record"] = incident
        state["log_snapshot"] = log_snapshot

        logger.info(
            f"Incident persisted: {incident.incident_id} (status: {incident.status})"
        )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Incident persistence failed: {str(e)}"
        ]
        logger.error(f"Incident persistence error: {e}", exc_info=True)
        raise


# ============================================================================
# NODE 7: NOTIFY INCIDENT
# ============================================================================


async def node_notify_incident(state: MonitoringGraphState) -> MonitoringGraphState:
    """Notify interested recipients about the incident.

    This step is intentionally lightweight because monitoring now focuses on recipient-based routing.

    Args:
        state: Graph state with incident_record

    Returns:
        Updated state
    """
    try:
        incident = state.get("incident_record")

        if not incident:
            logger.warning("No incident record to notify")
            return state

        # PLACEHOLDER: Notification logic should publish to subscribers or notification bridge.
        logger.info(
            "Publishing incident %s to recipient %s (concerned_users=%s)",
            incident.incident_id,
            incident.concerned_person.get("display_name") if incident.concerned_person else None,
            incident.concerned_users,
        )

        # Actual notification path can be added here once the monitor service bridge is wired.
        # For example: await publish_incident_to_subscribers(incident)

        logger.info(f"Incident notification published for {incident.incident_id}")

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Incident notification failed: {str(e)}"
        ]
        logger.error(f"Incident notification error: {e}", exc_info=True)
        return state


# ============================================================================
# GRAPH COMPILATION
# ============================================================================


def build_monitoring_graph():
    """Build and compile the monitoring graph.

    Returns:
        Compiled LangGraph DAG ready for execution
    """
    graph = StateGraph(MonitoringGraphState)

    # Add nodes
    graph.add_node("extract_event", node_extract_event)
    graph.add_node("decide_tools", node_decide_tools)
    graph.add_node("collect_diagnostics", node_collect_diagnostics)
    graph.add_node("classify_severity", node_classify_severity)
    graph.add_node("resolve_recipient", node_resolve_recipient)
    graph.add_node("persist_incident", node_persist_incident)
    graph.add_node("notify_incident", node_notify_incident)

    # Define flow
    graph.set_entry_point("extract_event")
    graph.add_edge("extract_event", "decide_tools")
    graph.add_edge("decide_tools", "collect_diagnostics")
    graph.add_edge("collect_diagnostics", "classify_severity")
    graph.add_edge("classify_severity", "resolve_recipient")
    graph.add_edge("resolve_recipient", "persist_incident")
    graph.add_edge("persist_incident", "notify_incident")
    graph.set_finish_point("notify_incident")

    return graph.compile()


def _build_tool_parameters(
    event: EnrichedEventInput, tools: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Build parameters for each tool based on event."""
    params = {}
    additional_context = event.additional_context or {}

    for tool_name in tools:
        if tool_name in [
            "get_pod_logs",
            "get_pod_events",
            "get_pod_status",
            "get_pod_metrics",
            "describe_pod",
        ]:
            params[tool_name] = {
                "namespace": event.namespace,
                "pod_name": event.resource_name,
            }
        elif tool_name in ["get_deployment_info", "describe_deployment"]:
            deployment_name = additional_context.get("deployment_name")
            if deployment_name:
                params[tool_name] = {
                    "namespace": event.namespace,
                    "deployment_name": deployment_name,
                }
            elif event.resource_type in [ResourceType.DEPLOYMENT, ResourceType.STATEFULSET]:
                params[tool_name] = {
                    "namespace": event.namespace,
                    "deployment_name": event.resource_name,
                }
            else:
                logger.warning(
                    "Skipping %s because no owning deployment name is available for %s/%s",
                    tool_name,
                    event.namespace,
                    event.resource_name,
                )
        elif tool_name == "list_nodes":
            params[tool_name] = {}
        elif tool_name in ["get_hpa_info", "detect_hpa_issues"]:
            params[tool_name] = {
                "namespace": event.namespace,
                "hpa_name": event.resource_name,
            }

    return params


def _parse_memory_value(value: str) -> int:
    """Parse memory value string (e.g., '512Mi') to bytes."""
    if not value:
        return 0

    value = value.upper()
    multipliers = {"MI": 1024 * 1024, "GI": 1024 * 1024 * 1024, "KI": 1024}

    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return int(value[: -len(suffix)]) * mult
            except ValueError:
                return 0

    return 0


def _is_tool_read_only(tool_name: str, tool_definitions: List[Any]) -> bool:
    """Return True if the named tool is marked read-only in definitions."""
    for t in tool_definitions:
        try:
            if t.name == tool_name:
                return bool(getattr(t, "is_read_only", True))
        except Exception:
            continue
    return True


def _build_log_snapshot(diagnostics: Dict[str, DiagnosticResult], max_lines: int = 8) -> Optional[str]:
    """Extract a compact log excerpt from diagnostic outputs."""
    candidates: list[str] = []

    for key in ("get_pod_logs", "describe_pod"):
        result = diagnostics.get(key)
        if not result or not result.success or not result.data:
            continue

        payload = result.data
        for field_name in ("logs", "prev_logs"):
            value = payload.get(field_name)
            if isinstance(value, str):
                lines = [line for line in value.splitlines() if line.strip()]
                if lines:
                    candidates.extend(lines[:max_lines])
            elif isinstance(value, dict):
                for container_name, container_logs in value.items():
                    if isinstance(container_logs, str):
                        lines = [line for line in container_logs.splitlines() if line.strip()]
                        if lines:
                            candidates.append(f"[{container_name}]")
                            candidates.extend(lines[:max_lines])
                    elif isinstance(container_logs, list):
                        cleaned = [str(line) for line in container_logs if str(line).strip()]
                        if cleaned:
                            candidates.append(f"[{container_name}]")
                            candidates.extend(cleaned[:max_lines])

        if candidates:
            break

    if not candidates:
        return None

    return "\n".join(candidates[:max_lines])


def _extract_json_payload(text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw LLM output.

    Handles plain JSON and fenced markdown blocks like:
    ```json
    {...}
    ```
    """
    stripped = text.strip()

    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        lines = stripped.splitlines()
        if lines and lines[0].strip().lower() in {"json", "javascript"}:
            lines = lines[1:]
        stripped = "\n".join(lines).strip()

    def _load_with_repair(candidate: str) -> Dict[str, Any]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
            return json.loads(repaired)

    if stripped.startswith("{") and stripped.endswith("}"):
        return _load_with_repair(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return _load_with_repair(stripped[start : end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)


def _diagnostics_to_prompt_payload(diagnostics: Dict[str, DiagnosticResult]) -> Dict[str, Any]:
    """Convert live diagnostic results into prompt-safe JSON."""
    payload: Dict[str, Any] = {}
    for name, result in diagnostics.items():
        payload[name] = {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }
    return payload


def _coerce_number(value: Any, default: float = 0.5) -> float:
    """Coerce LLM numeric fields into floats."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        label_map = {
            "low": 0.25,
            "medium": 0.5,
            "high": 0.75,
            "very low": 0.1,
            "very high": 0.9,
        }
        if normalized in label_map:
            return label_map[normalized]
        try:
            return float(normalized)
        except ValueError:
            return default
    return default


def _coerce_int(value: Any, default: int) -> int:
    """Coerce LLM integer-like fields into ints."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        label_map = {"low": 1, "medium": 2, "high": 3, "very low": 1, "very high": 4}
        if normalized in label_map:
            return label_map[normalized]
        try:
            return int(float(normalized))
        except ValueError:
            return default
    return default


def _coerce_list(value: Any) -> List[str]:
    """Coerce a potentially scalar LLM field into a cleaned list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _normalize_root_cause_analysis(raw_analysis: Any) -> RootCauseAnalysis:
    """Normalize the model root-cause payload into the typed schema."""
    if not isinstance(raw_analysis, dict):
        raise ValueError("LLM did not return a valid root_cause_analysis object")

    return RootCauseAnalysis(
        root_cause=str(raw_analysis.get("root_cause", "")).strip() or "LLM did not supply a root cause",
        hypothesis_confidence=_coerce_number(raw_analysis.get("hypothesis_confidence"), default=0.5),
        supporting_evidence=_coerce_list(raw_analysis.get("supporting_evidence")),
        reasoning=str(raw_analysis.get("reasoning", "")).strip(),
    )


def _normalize_remediation_item(
    item: Any,
    step_number: int,
    allowed_action_tools: Optional[List[str]] = None,
) -> Optional[RemediationStep]:
    """Normalize one LLM remediation step into the typed schema."""
    if not isinstance(item, dict):
        return None

    action_type = str(item.get("action_type") or item.get("action") or "").strip()
    if not action_type:
        return None
    if allowed_action_tools is not None and action_type not in allowed_action_tools:
        return None

    return RemediationStep(
        step_number=_coerce_int(item.get("step_number"), step_number),
        action_type=action_type,
        description=str(item.get("description") or item.get("summary") or action_type).strip(),
        target_resource=str(item.get("target_resource") or item.get("target") or "").strip(),
        why=str(item.get("why") or item.get("rationale") or "").strip(),
        evidence=_coerce_list(item.get("evidence")),
        estimated_risk=str(item.get("estimated_risk") or "LOW").strip().upper(),
    )


def _normalize_evidence_map(raw_map: Any) -> Dict[str, List[str]]:
    """Normalize the model evidence-map payload into a dict of string lists."""
    if not isinstance(raw_map, dict):
        return {}

    normalized: Dict[str, List[str]] = {}
    for key, value in raw_map.items():
        normalized[str(key)] = _coerce_list(value)
    return normalized


async def _run_llm_incident_analysis(
    event: EnrichedEventInput,
    diagnostics: Dict[str, DiagnosticResult],
) -> Dict[str, Any]:
    """Ask the LLM for the full incident analysis payload."""
    llm_client = get_llm_client()
    tool_definitions = get_tool_definitions()
    allowed_action_tools = [name for name in ALLOWED_BASIC_ACTION_TOOLS if name in {tool.name for tool in tool_definitions}]
    prompt = f"""
You are a Kubernetes incident analyst.

Return only JSON with these keys:
- severity: one of INFO, WARNING, CRITICAL
- root_cause_analysis: an object with keys root_cause, hypothesis_confidence, supporting_evidence, reasoning
- summary: a short one-line incident summary
- detailed_summary: a concise but complete incident summary using the live diagnostics
- suggested_actions: a list of remediation suggestions with keys action_type, description, target_resource, priority, estimated_risk, rationale, evidence
- remediation_plan: an ordered list of handoff steps with keys step_number, action_type, description, target_resource, why, evidence, estimated_risk
- evidence_map: a mapping from action_type to supporting evidence snippets

Allowed action tools:
{", ".join(allowed_action_tools)}

Rules:
- Use only the event details and live diagnostics below.
- Do not invent facts.
- Keep fixes basic and practical.
- Use only the allowed action tool names above.
- Prefer 1-2 small-scope actions.
- If evidence is insufficient, say so explicitly in the root cause and summary.
- Do not output markdown or commentary.

EVENT:
{json.dumps({
    "resource_type": event.resource_type,
    "resource_name": event.resource_name,
    "namespace": event.namespace,
    "reason": event.reason,
    "severity": event.severity,
    "message": event.message,
    "additional_context": event.additional_context,
}, indent=2)}

LIVE DIAGNOSTICS:
{json.dumps(_diagnostics_to_prompt_payload(diagnostics), indent=2, default=str)}

LOG SNAPSHOT:
{_build_log_snapshot(diagnostics) or ""}
""".strip()

    response = await llm_client.ainvoke(
        [
            {
                "role": "system",
                "content": (
                    "You are a Kubernetes incident analyst. Return only valid JSON and do not use fallback or heuristic language."
                ),
            },
            {"role": "user", "content": prompt},
        ]
    )
    llm_response_text = llm_client.extract_text(response)
    logger.debug("LLM incident-analysis response text: %s", llm_response_text)
    logger.debug("LLM raw response object: %s", response)
    if not llm_response_text:
        raise ValueError("LLM returned an empty incident-analysis response")

    payload = _extract_json_payload(llm_response_text)
    payload["_response_model"] = str(response.get("model") or response.get("id") or llm_client.model).strip()
    payload["_response_source"] = "live_nvidia_api"
    payload["_configured_model"] = llm_client.model
    return payload


