"""Monitoring graph: Automated incident detection and diagnostics.

LangGraph DAG that:
1. Extracts and normalizes Kubernetes events
2. Uses LLM to decide which diagnostic tools to call
3. Collects diagnostics
4. Classifies severity
5. Resolves team ownership
6. Persists incident record
7. Notifies team
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

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
from app.agent.config import get_llm_client, LLM_CONFIG

logger = logging.getLogger(__name__)


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

        # Validate event schema
        if isinstance(event, dict):
            event = EnrichedEventInput(**event)
        elif not isinstance(event, EnrichedEventInput):
            raise ValueError(
                f"Invalid event type: {type(event)}. Expected dict or EnrichedEventInput"
            )

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
        # Include category and read-only flag to help the LLM distinguish actions
        tools_description = "\n".join(
            [f"- {t.name} (category={t.category}, read_only={t.is_read_only}): {t.description}" for t in tool_definitions]
        )

        few_shot_examples = """
FEW-SHOT EXAMPLES:
1) CrashLoopBackOff with log evidence of OOM:
{
    "tools": ["get_pod_logs", "get_pod_metrics", "get_pod_status"],
    "suggested_actions": ["increase_memory_limit", "restart_pod"],
    "remediation_plan": [
        {"step_number": 1, "action_type": "increase_memory_limit", "description": "Increase pod memory limit", "target_resource": "namespace/pod", "why": "Logs and metrics show the container is hitting memory pressure", "evidence": ["OOMKilled", "memory usage near limit"], "estimated_risk": "LOW"},
        {"step_number": 2, "action_type": "restart_pod", "description": "Restart pod after memory fix is reviewed", "target_resource": "namespace/pod", "why": "A restart may recover once the resource issue is fixed", "evidence": ["CrashLoopBackOff"], "estimated_risk": "LOW"}
    ],
    "evidence_map": {"increase_memory_limit": ["OOMKilled", "memory usage near limit"], "restart_pod": ["CrashLoopBackOff"]},
    "reasoning": "OOM evidence is strongest; collect logs and metrics first, then recommend memory fix before restart."
}

2) HPA unable to fetch metrics:
{
    "tools": ["get_hpa_info", "detect_hpa_issues", "list_nodes"],
    "suggested_actions": ["verify_metrics_server", "validate_hpa_target_metrics"],
    "remediation_plan": [
        {"step_number": 1, "action_type": "verify_metrics_server", "description": "Verify metrics-server is installed and metrics.k8s.io API is healthy", "target_resource": "cluster", "why": "HPA metrics are unavailable from the cluster", "evidence": ["metrics.k8s.io unavailable"], "estimated_risk": "LOW"},
        {"step_number": 2, "action_type": "validate_hpa_target_metrics", "description": "Validate HPA target workload exposes CPU/memory metrics and requests", "target_resource": "namespace/hpa", "why": "After metrics-server is healthy, confirm the workload exports metrics", "evidence": ["FailedGetResourceMetric"], "estimated_risk": "LOW"}
    ],
    "evidence_map": {"verify_metrics_server": ["metrics.k8s.io unavailable"], "validate_hpa_target_metrics": ["FailedGetResourceMetric"]},
    "reasoning": "The cluster metrics pipeline is the blocker, so verify it before touching the target workload."
}
""".strip()

        prompt = f"""
You are a Kubernetes diagnostics expert. An incident has occurred in the cluster.

EVENT DETAILS:
- Resource Type: {event.resource_type}
- Resource Name: {event.resource_name}
- Namespace: {event.namespace}
- Reason: {event.reason}
- Severity: {event.severity}
- Message: {event.message}
- Additional Context: {json.dumps(event.additional_context, indent=2)}

AVAILABLE DIAGNOSTIC TOOLS:
{tools_description}
{few_shot_examples}
Note: Some tools are actions (will mutate cluster state) and require explicit approval.
Return two lists:
1) `tools`: read-only diagnostic/query tools the agent should execute now.
2) `suggested_actions`: action/mutation tools you would recommend (do not execute without approval).
Also return `remediation_plan` and `evidence_map`.

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

        # Parse LLM response
        try:
            response_json = _extract_json_payload(llm_response_text)
            tools_to_call = response_json.get("tools", [])
            suggested_actions = response_json.get("suggested_actions", [])
            remediation_plan = response_json.get("remediation_plan", [])
            evidence_map = response_json.get("evidence_map", {})
            llm_reasoning = response_json.get("reasoning", "")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {llm_response_text}")
            tools_to_call = _get_default_tools_for_reason(event.reason)
            suggested_actions = []
            remediation_plan = []
            evidence_map = {}
            llm_reasoning = "Fallback to default tools due to LLM parse error"

        # Only keep known tools
        raw_tools = [tool for tool in tools_to_call if tool in tool_names]
        raw_suggested_actions = [tool for tool in suggested_actions if tool in tool_names]

        # Sanitize and separate read-only diagnostics vs actions
        sanitized = _sanitize_tools_for_resource(event, raw_tools)
        # Heuristic: if severity is CRITICAL, ensure at least one deep diagnostic (describe_deployment/describe_pod)
        if event.severity == SeverityLevel.CRITICAL:
            if event.resource_type == ResourceType.POD and "describe_pod" in tool_names and "describe_pod" not in sanitized:
                sanitized.append("describe_pod")

        # Store diagnostics to execute now (read-only only). Action tools are kept separately.
        state["tools_to_call"] = [t for t in sanitized if _is_tool_read_only(t, tool_definitions)]
        state["suggested_action_tools"] = [t for t in raw_suggested_actions if not _is_tool_read_only(t, tool_definitions)]
        state["remediation_plan"] = _normalize_remediation_plan(remediation_plan)
        state["evidence_map"] = _normalize_evidence_map(evidence_map)
        state["llm_tool_reasoning"] = llm_reasoning

        logger.info(
            f"LLM selected tools: {tools_to_call}, suggested_actions: {suggested_actions}. Reasoning: {llm_reasoning}"
        )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Tool selection failed: {str(e)}"
        ]
        logger.error(f"Tool selection error: {e}", exc_info=True)
        state["tools_to_call"] = _get_default_tools_for_reason(state["event"].reason)
        return state


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


def node_classify_severity(state: MonitoringGraphState) -> MonitoringGraphState:
    """Classify incident severity based on diagnostics and rules.

    Uses deterministic rules to classify severity (not LLM).

    Args:
        state: Graph state with diagnostics

    Returns:
        Updated state with severity and root_cause_analysis
    """
    try:
        event = state["event"]
        diagnostics = state.get("collected_diagnostics", {})

        # Deterministic severity rules
        severity = event.severity  # Start with event severity

        # Check specific patterns in diagnostics
        for tool_name, result in diagnostics.items():
            if not result.success or not result.data:
                continue

            # OOMKilled pattern
            if (
                tool_name == "get_pod_metrics"
                and result.data.get("memory_usage")
                and result.data.get("memory_limit")
            ):
                usage = _parse_memory_value(result.data.get("memory_usage", "0Mi"))
                limit = _parse_memory_value(result.data.get("memory_limit", "1Gi"))
                if usage > limit * 0.9:  # 90%+ usage
                    severity = SeverityLevel.CRITICAL
                    break

            # High restart count
            if tool_name == "get_pod_status":
                restart_count = result.data.get("restart_count", 0)
                if restart_count > 5:
                    severity = SeverityLevel.CRITICAL
                    break

        # Generate root cause hypothesis
        root_cause = _analyze_root_cause(event, diagnostics)

        state["severity"] = severity
        state["root_cause_analysis"] = root_cause

        logger.info(
            f"Classified severity: {severity}. Root cause: {root_cause.root_cause}"
        )

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Severity classification failed: {str(e)}"
        ]
        logger.error(f"Severity classification error: {e}", exc_info=True)
        return state


# ============================================================================
# NODE 5: RESOLVE TEAM OWNERSHIP
# ============================================================================


def node_resolve_team(state: MonitoringGraphState) -> MonitoringGraphState:
    """Resolve which team owns this incident.

    Uses event.teams from monitoring pipeline (already resolved).

    Args:
        state: Graph state with event

    Returns:
        Updated state with teams
    """
    try:
        event = state["event"]

        # Teams are already resolved in monitoring pipeline
        # This node just passes them through for consistency
        teams = event.teams

        state["teams"] = teams

        logger.info(f"Resolved teams: {teams}")

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Team resolution failed: {str(e)}"
        ]
        logger.error(f"Team resolution error: {e}", exc_info=True)
        state["teams"] = []
        return state


# ============================================================================
# NODE 5B: RESOLVE RECIPIENT
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
                "No specific recipient resolved for %s/%s; notification will fall back to team routing",
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
    """Create and persist incident record to database.

    PLACEHOLDER: Actual database persistence goes here.

    Args:
        state: Graph state with all investigation data

    Returns:
        Updated state with incident_record
    """
    try:
        event = state["event"]
        diagnostics = state.get("collected_diagnostics", {})
        severity = state.get("severity", event.severity)
        teams = state.get("teams", [])
        root_cause = state.get("root_cause_analysis")
        concerned_person = state.get("concerned_person")
        concerned_users = state.get("concerned_users", [])
        owner_hints = state.get("owner_hints", [])
        log_snapshot = _build_log_snapshot(diagnostics)
        remediation_plan = state.get("remediation_plan", [])
        evidence_map = state.get("evidence_map", {})
        if not remediation_plan:
            remediation_plan = _build_remediation_plan(event, root_cause, diagnostics)

        suggested_actions = _generate_suggested_actions(event, root_cause)

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
            teams=teams,
            summary=f"{event.reason} in {event.namespace}/{event.resource_name}",
            detailed_summary=_build_detailed_summary(
                event,
                diagnostics,
                concerned_person=concerned_person,
                log_snapshot=log_snapshot,
                remediation_plan=remediation_plan,
                evidence_map=evidence_map,
            ),
            log_snapshot=log_snapshot,
            collected_diagnostics={
                name: result.dict() for name, result in diagnostics.items()
            },
            tools_called=list(diagnostics.keys()),
            llm_reasoning=state.get("llm_tool_reasoning"),
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

        # PLACEHOLDER: Save to database
        logger.info(
            f"[PLACEHOLDER] Persisting incident {incident.incident_id} to database"
        )
        # from app.database.models import IncidentRecord as IncidentRecordModel
        # session.add(IncidentRecordModel(**incident.dict()))
        # session.commit()

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
        return state


# ============================================================================
# NODE 7: NOTIFY TEAM
# ============================================================================


async def node_notify_team(state: MonitoringGraphState) -> MonitoringGraphState:
    """Notify team of incident via WebSocket and/or other channels.

    PLACEHOLDER: Send notifications to team members.

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

        # PLACEHOLDER: Send WebSocket notification
        logger.info(
            "Notifying teams %s and recipient %s for incident %s",
            incident.teams,
            incident.concerned_person.get("display_name") if incident.concerned_person else None,
            incident.incident_id,
        )

        # from app.api.routes.events import notify_incident
        # await notify_incident(incident)

        logger.info(f"Teams notified for incident {incident.incident_id}")

        return state

    except Exception as e:
        state["errors"] = state.get("errors", []) + [
            f"Team notification failed: {str(e)}"
        ]
        logger.error(f"Team notification error: {e}", exc_info=True)
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
    graph.add_node("resolve_team", node_resolve_team)
    graph.add_node("resolve_recipient", node_resolve_recipient)
    graph.add_node("persist_incident", node_persist_incident)
    graph.add_node("notify_team", node_notify_team)

    # Define flow
    graph.set_entry_point("extract_event")
    graph.add_edge("extract_event", "decide_tools")
    graph.add_edge("decide_tools", "collect_diagnostics")
    graph.add_edge("collect_diagnostics", "classify_severity")
    graph.add_edge("classify_severity", "resolve_team")
    graph.add_edge("resolve_team", "resolve_recipient")
    graph.add_edge("resolve_recipient", "persist_incident")
    graph.add_edge("persist_incident", "notify_team")
    graph.set_finish_point("notify_team")

    return graph.compile()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _get_placeholder_llm_response(resource_type: str, reason: str) -> str:
    """Get placeholder LLM response for testing.

    REMOVE when LLM is integrated.
    """
    # Default tools by reason
    reason_map = {
        "CrashLoopBackOff": [
            "get_pod_logs",
            "get_pod_events",
            "get_pod_status",
            "get_pod_metrics",
        ],
        "OOMKilled": ["get_pod_logs", "get_pod_metrics", "get_pod_status"],
        "ImagePullBackOff": ["get_pod_events", "get_pod_status"],
        "FailedScheduling": ["get_pod_events", "get_pod_status", "list_nodes"],
        "Evicted": ["get_pod_status", "list_nodes"],
        "Pending": ["get_pod_events", "get_pod_status"],
    }

    tools = reason_map.get(reason, ["get_pod_logs", "get_pod_events", "get_pod_status"])

    return json.dumps(
        {
            "tools": tools,
            "reasoning": f"Selected tools based on {reason} pattern",
        }
    )


def _get_default_tools_for_reason(reason: str) -> List[str]:
    """Get default tools for a given failure reason."""
    reason_map = {
        "CrashLoopBackOff": [
            "get_pod_logs",
            "get_pod_events",
            "get_pod_status",
            "get_pod_metrics",
        ],
        "OOMKilled": ["get_pod_logs", "get_pod_metrics", "get_pod_status"],
        "ImagePullBackOff": ["get_pod_events", "get_pod_status"],
        "FailedScheduling": ["get_pod_events", "get_pod_status", "list_nodes"],
        "FailedGetResourceMetric": ["get_hpa_info", "detect_hpa_issues", "list_nodes"],
        "Evicted": ["get_pod_status", "list_nodes"],
        "Pending": ["get_pod_events", "get_pod_status"],
    }
    return reason_map.get(reason, ["get_pod_logs", "get_pod_events", "get_pod_status"])


def _sanitize_tools_for_resource(
    event: EnrichedEventInput, tools: List[str]
) -> List[str]:
    """Filter/select tools that are valid for the resource type."""
    if event.resource_type == ResourceType.HPA:
        allowed_for_hpa = {"get_hpa_info", "detect_hpa_issues", "list_nodes"}
        selected = [tool for tool in tools if tool in allowed_for_hpa]
        if not selected:
            selected = ["get_hpa_info", "detect_hpa_issues", "list_nodes"]
        return selected

    if event.resource_type == ResourceType.POD:
        allowed_for_pod = {
            "get_pod_logs",
            "get_pod_events",
            "get_pod_status",
            "get_pod_metrics",
            "describe_pod",
            "list_nodes",
            "get_deployment_info",
            "describe_deployment",
        }
        selected = [tool for tool in tools if tool in allowed_for_pod]

        # Deployment-only diagnostics require owning deployment context.
        additional_context = event.additional_context or {}
        if not additional_context.get("deployment_name"):
            selected = [
                tool
                for tool in selected
                if tool not in {"get_deployment_info", "describe_deployment"}
            ]

        if not selected:
            selected = ["get_pod_logs", "get_pod_events", "get_pod_status"]
        return selected

    return tools


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


def _analyze_root_cause(
    event: EnrichedEventInput, diagnostics: Dict[str, DiagnosticResult]
) -> RootCauseAnalysis:
    """Analyze root cause based on event and diagnostics."""
    evidence = []
    root_cause_text = f"Unknown cause of {event.reason}"
    confidence = 0.5

    # CrashLoopBackOff analysis
    if event.reason in {"CrashLoopBackOff", "BackOff"}:
        root_cause_text = "Application container is crashing repeatedly"
        evidence.append(f"{event.reason} detected")

        # Check metrics for OOM
        metrics_result = diagnostics.get("get_pod_metrics")
        if metrics_result and metrics_result.success:
            usage = _parse_memory_value(
                metrics_result.data.get("memory_usage", "0Mi")
            )
            limit = _parse_memory_value(metrics_result.data.get("memory_limit", "1Gi"))
            if usage > limit * 0.9:
                root_cause_text = "Application out of memory (OOMKilled)"
                evidence.append("Memory usage near limit")
                confidence = 0.9

        # Check logs for errors
        logs_result = diagnostics.get("get_pod_logs")
        if logs_result and logs_result.success:
            logs = logs_result.data.get("logs", [])
            if any("error" in line.lower() for line in logs):
                evidence.append("Application errors found in logs")
                if confidence < 0.8:
                    confidence = 0.8

    # OOMKilled analysis
    elif event.reason == "OOMKilled":
        root_cause_text = "Application terminated due to out of memory"
        evidence.append("OOMKilled event detected")
        confidence = 0.95

    # ImagePullBackOff analysis
    elif event.reason == "ImagePullBackOff":
        root_cause_text = "Container image cannot be pulled from registry"
        evidence.append("ImagePullBackOff detected")
        confidence = 0.9

    # FailedScheduling analysis
    elif event.reason == "FailedScheduling":
        root_cause_text = "Pod cannot be scheduled on available nodes"
        evidence.append("FailedScheduling detected")

        nodes_result = diagnostics.get("list_nodes")
        if nodes_result and nodes_result.success:
            nodes = nodes_result.data.get("nodes", [])
            if len(nodes) == 0:
                evidence.append("No nodes available in cluster")
                confidence = 0.9

    # HPA metric acquisition failures
    elif event.reason == "FailedGetResourceMetric":
        root_cause_text = "HPA cannot fetch resource metrics from metrics API"
        evidence.append("FailedGetResourceMetric detected")
        message = (event.message or "").lower()
        if "metrics.k8s.io" in message or "could not find the requested resource" in message:
            evidence.append("metrics.k8s.io API unavailable or metrics-server not installed")
            confidence = 0.95
        else:
            confidence = 0.8

    return RootCauseAnalysis(
        root_cause=root_cause_text,
        hypothesis_confidence=confidence,
        supporting_evidence=evidence,
        reasoning=f"Based on {event.reason} event and diagnostic data",
    )


def _build_detailed_summary(
    event: EnrichedEventInput,
    diagnostics: Dict[str, DiagnosticResult],
    concerned_person: Optional[Dict[str, Any]] = None,
    log_snapshot: Optional[str] = None,
    remediation_plan: Optional[List[RemediationStep]] = None,
    evidence_map: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Build detailed summary of incident."""
    lines = [
        f"Event: {event.reason}",
        f"Resource: {event.resource_type} {event.namespace}/{event.resource_name}",
        f"Severity: {event.severity}",
        f"Message: {event.message}",
        f"Diagnostics collected: {len(diagnostics)} tools",
    ]

    if concerned_person:
        display_name = concerned_person.get("display_name") or concerned_person.get("username")
        email = concerned_person.get("email")
        lines.append(f"Concerned person: {display_name} ({email})" if email else f"Concerned person: {display_name}")

    if log_snapshot:
        lines.append("Log snapshot:")
        lines.extend(f"  {line}" for line in log_snapshot.splitlines())

    if remediation_plan:
        lines.append("Remediation handoff:")
        for step in remediation_plan:
            evidence_text = ", ".join(step.evidence) if step.evidence else "no evidence quoted"
            lines.append(
                f"  {step.step_number}. {step.action_type}: {step.description}"
            )
            lines.append(f"     target={step.target_resource}; why={step.why}; risk={step.estimated_risk}")
            lines.append(f"     evidence={evidence_text}")

    if evidence_map:
        lines.append("Evidence map:")
        for action_type, snippets in evidence_map.items():
            joined = "; ".join(snippets)
            lines.append(f"  {action_type}: {joined}")

    return "\n".join(lines)


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

    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start : end + 1])

    raise json.JSONDecodeError("No JSON object found", text, 0)


def _normalize_evidence_map(raw_map: Any) -> Dict[str, List[str]]:
    """Normalize an LLM evidence map into a simple tool -> snippets mapping."""
    normalized: Dict[str, List[str]] = {}
    if not isinstance(raw_map, dict):
        return normalized

    for key, value in raw_map.items():
        if isinstance(value, list):
            snippets = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str):
            snippets = [value.strip()] if value.strip() else []
        else:
            snippets = [str(value).strip()] if str(value).strip() else []

        if snippets:
            normalized[str(key)] = snippets
    return normalized


def _canonicalize_action_type(action_type: str) -> str:
    """Map LLM-generated action labels to stable canonical names where possible."""
    normalized = (action_type or "").strip().lower()
    aliases = {
        "verify_metrics_server_installation": "verify_metrics_server",
        "verify_metrics_server": "verify_metrics_server",
        "check_metrics_server": "verify_metrics_server",
        "validate_hpa_target_metrics": "validate_hpa_target_metrics",
        "restart_pod": "restart_pod",
        "rollout_restart": "rollout_restart",
        "scale_deployment": "scale_deployment",
        "increase_memory_limit": "increase_memory_limit",
        "check_logs": "check_logs",
        "add_nodes": "add_nodes",
    }
    return aliases.get(normalized, action_type)


def _normalize_remediation_plan(raw_plan: Any) -> List[RemediationStep]:
    """Convert raw LLM remediation plan objects into typed, ordered steps."""
    if not isinstance(raw_plan, list):
        return []

    steps: List[RemediationStep] = []
    for index, item in enumerate(raw_plan, start=1):
        if not isinstance(item, dict):
            continue

        evidence = item.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        elif not isinstance(evidence, list):
            evidence = [str(evidence)] if evidence is not None else []

        try:
            steps.append(
                RemediationStep(
                    step_number=int(item.get("step_number") or index),
                    action_type=_canonicalize_action_type(str(item.get("action_type") or "unknown")),
                    description=str(item.get("description") or ""),
                    target_resource=str(item.get("target_resource") or ""),
                    why=str(item.get("why") or ""),
                    evidence=[str(value).strip() for value in evidence if str(value).strip()],
                    estimated_risk=str(item.get("estimated_risk") or "LOW"),
                )
            )
        except Exception:
            continue

    steps.sort(key=lambda step: step.step_number)
    return steps


def _generate_suggested_actions(
    event: EnrichedEventInput, root_cause: Optional[RootCauseAnalysis]
) -> List[SuggestedAction]:
    """Generate suggested remediation actions."""
    actions = []

    if not root_cause:
        return actions

    # CrashLoopBackOff suggestions
    if event.reason in {"CrashLoopBackOff", "BackOff"}:
        if "OOMKilled" in root_cause.root_cause:
            actions.append(
                SuggestedAction(
                    action_type="increase_memory_limit",
                    description="Increase pod memory limit",
                    target_resource=f"{event.namespace}/{event.resource_name}",
                    priority=1,
                    estimated_risk="LOW",
                    rationale="Root cause points to memory pressure/OOM",
                    evidence=["OOMKilled"],
                )
            )
        else:
            actions.append(
                SuggestedAction(
                    action_type="restart_pod",
                    description="Restart pod to clear transient issues",
                    target_resource=f"{event.namespace}/{event.resource_name}",
                    priority=2,
                    estimated_risk="LOW",
                    rationale="CrashLoopBackOff commonly needs a restart after diagnosis",
                    evidence=[event.reason],
                )
            )
            actions.append(
                SuggestedAction(
                    action_type="check_logs",
                    description="Review application logs for errors",
                    target_resource=f"{event.namespace}/{event.resource_name}",
                    priority=1,
                    estimated_risk="LOW",
                    rationale="Logs are the strongest next evidence source for a crash loop",
                    evidence=[event.reason],
                )
            )

    # ImagePullBackOff suggestions
    elif event.reason == "ImagePullBackOff":
        actions.append(
            SuggestedAction(
                action_type="check_image_registry",
                description="Verify image exists in registry and credentials are valid",
                target_resource=f"{event.namespace}/{event.resource_name}",
                priority=1,
                estimated_risk="LOW",
                rationale="Image pull failures usually come from registry/image config",
                evidence=[event.reason],
            )
        )

    # FailedScheduling suggestions
    elif event.reason == "FailedScheduling":
        actions.append(
            SuggestedAction(
                action_type="add_nodes",
                description="Add more nodes to cluster",
                target_resource="cluster",
                priority=2,
                estimated_risk="MEDIUM",
                rationale="Insufficient capacity or scheduling constraints are the likely cause",
                evidence=[event.reason],
            )
        )

    elif event.reason == "FailedGetResourceMetric":
        actions.append(
            SuggestedAction(
                action_type="verify_metrics_server",
                description="Verify metrics-server is installed and metrics.k8s.io API is healthy",
                target_resource="cluster",
                priority=1,
                estimated_risk="LOW",
                rationale="The HPA cannot fetch resource metrics from the cluster",
                evidence=[event.reason, root_cause.root_cause],
            )
        )
        actions.append(
            SuggestedAction(
                action_type="validate_hpa_target_metrics",
                description="Validate HPA target workload exposes CPU/memory metrics and requests",
                target_resource=f"{event.namespace}/{event.resource_name}",
                priority=2,
                estimated_risk="LOW",
                rationale="Once metrics are available, verify the target workload is configured correctly",
                evidence=[event.reason],
            )
        )

    # Preserve only highest-priority actions first.
    actions.sort(key=lambda item: item.priority)
    return actions[:3]


def _build_remediation_plan(
    event: EnrichedEventInput,
    root_cause: Optional[RootCauseAnalysis],
    diagnostics: Dict[str, DiagnosticResult],
) -> List[RemediationStep]:
    """Build an ordered remediation handoff from the available evidence."""
    suggested_actions = _generate_suggested_actions(event, root_cause)
    plan: List[RemediationStep] = []

    for index, action in enumerate(suggested_actions, start=1):
        evidence = list(getattr(action, "evidence", []) or [])
        if not evidence and root_cause:
            evidence = list(root_cause.supporting_evidence)

        plan.append(
            RemediationStep(
                step_number=index,
                action_type=action.action_type,
                description=action.description,
                target_resource=action.target_resource,
                why=(action.rationale or root_cause.reasoning) if root_cause else "Evidence indicates this is the next best action",
                evidence=evidence,
                estimated_risk=action.estimated_risk,
            )
        )

    # If we still do not have a plan, provide a conservative handoff.
    if not plan:
        fallback_evidence = root_cause.supporting_evidence if root_cause else [event.reason]
        plan.append(
            RemediationStep(
                step_number=1,
                action_type="investigate_further",
                description="Review the collected diagnostics and expand evidence gathering",
                target_resource=f"{event.namespace}/{event.resource_name}",
                why="The agent does not have enough evidence to recommend a safer remediation step",
                evidence=fallback_evidence,
                estimated_risk="LOW",
            )
        )

    return plan
