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
    ResourceType,
)
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
        tools_description = "\n".join(
            [f"- {t.name}: {t.description}" for t in tool_definitions]
        )

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

Based on the incident details, which diagnostic tools would you call to investigate?
Select only the most relevant tools (2-4 tools usually sufficient).

Respond in this JSON format:
{{
    "tools": ["tool_name1", "tool_name2", ...],
    "reasoning": "Why you selected these tools"
}}
"""

        # Call LLM
        # PLACEHOLDER: Replace with actual LLM client call
        llm_client = get_llm_client()

        logger.info(
            f"[PLACEHOLDER] Calling LLM to select tools for {event.resource_type} {event.resource_name}"
        )

        # PLACEHOLDER RESPONSE (remove when LLM is integrated)
        llm_response_text = _get_placeholder_llm_response(
            event.resource_type, event.reason
        )

        # Parse LLM response
        try:
            response_json = json.loads(llm_response_text)
            tools_to_call = response_json.get("tools", [])
            llm_reasoning = response_json.get("reasoning", "")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {llm_response_text}")
            tools_to_call = _get_default_tools_for_reason(event.reason)
            llm_reasoning = "Fallback to default tools due to LLM parse error"

        state["tools_to_call"] = tools_to_call
        state["llm_tool_reasoning"] = llm_reasoning

        logger.info(
            f"LLM selected tools: {tools_to_call}. Reasoning: {llm_reasoning}"
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
            detailed_summary=_build_detailed_summary(event, diagnostics),
            collected_diagnostics={
                name: result.dict() for name, result in diagnostics.items()
            },
            tools_called=list(diagnostics.keys()),
            llm_reasoning=state.get("llm_tool_reasoning"),
            root_cause_analysis=root_cause,
            suggested_actions=_generate_suggested_actions(event, root_cause),
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
            f"[PLACEHOLDER] Notifying teams {incident.teams} of incident {incident.incident_id}"
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
    graph.add_node("persist_incident", node_persist_incident)
    graph.add_node("notify_team", node_notify_team)

    # Define flow
    graph.set_entry_point("extract_event")
    graph.add_edge("extract_event", "decide_tools")
    graph.add_edge("decide_tools", "collect_diagnostics")
    graph.add_edge("collect_diagnostics", "classify_severity")
    graph.add_edge("classify_severity", "resolve_team")
    graph.add_edge("resolve_team", "persist_incident")
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
        "Evicted": ["get_pod_status", "list_nodes"],
        "Pending": ["get_pod_events", "get_pod_status"],
    }
    return reason_map.get(reason, ["get_pod_logs", "get_pod_events", "get_pod_status"])


def _build_tool_parameters(
    event: EnrichedEventInput, tools: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Build parameters for each tool based on event."""
    params = {}

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
            params[tool_name] = {
                "namespace": event.namespace,
                "deployment_name": event.resource_name,
            }
        elif tool_name == "list_nodes":
            params[tool_name] = {}

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


def _analyze_root_cause(
    event: EnrichedEventInput, diagnostics: Dict[str, DiagnosticResult]
) -> RootCauseAnalysis:
    """Analyze root cause based on event and diagnostics."""
    evidence = []
    root_cause_text = f"Unknown cause of {event.reason}"
    confidence = 0.5

    # CrashLoopBackOff analysis
    if event.reason == "CrashLoopBackOff":
        root_cause_text = "Application container is crashing repeatedly"
        evidence.append("CrashLoopBackOff detected")

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

    return RootCauseAnalysis(
        root_cause=root_cause_text,
        hypothesis_confidence=confidence,
        supporting_evidence=evidence,
        reasoning=f"Based on {event.reason} event and diagnostic data",
    )


def _build_detailed_summary(
    event: EnrichedEventInput, diagnostics: Dict[str, DiagnosticResult]
) -> str:
    """Build detailed summary of incident."""
    lines = [
        f"Event: {event.reason}",
        f"Resource: {event.resource_type} {event.namespace}/{event.resource_name}",
        f"Severity: {event.severity}",
        f"Message: {event.message}",
        f"Diagnostics collected: {len(diagnostics)} tools",
    ]

    return "\n".join(lines)


def _generate_suggested_actions(
    event: EnrichedEventInput, root_cause: Optional[RootCauseAnalysis]
) -> List[SuggestedAction]:
    """Generate suggested remediation actions."""
    actions = []

    if not root_cause:
        return actions

    # CrashLoopBackOff suggestions
    if event.reason == "CrashLoopBackOff":
        if "OOMKilled" in root_cause.root_cause:
            actions.append(
                SuggestedAction(
                    action_type="increase_memory_limit",
                    description="Increase pod memory limit",
                    target_resource=f"{event.namespace}/{event.resource_name}",
                    priority=1,
                    estimated_risk="LOW",
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
                )
            )
            actions.append(
                SuggestedAction(
                    action_type="check_logs",
                    description="Review application logs for errors",
                    target_resource=f"{event.namespace}/{event.resource_name}",
                    priority=1,
                    estimated_risk="LOW",
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
            )
        )

    return actions
