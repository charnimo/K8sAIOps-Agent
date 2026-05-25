"""LangGraph orchestration for the interactive Kubernetes agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from agent.agent_instructions import get_system_instruction


_MUTATION_WORDS = {
    "delete",
    "scale",
    "restart",
    "create",
    "patch",
    "update",
    "drain",
    "cordon",
    "uncordon",
    "suspend",
    "resume",
    "rollback",
}

_TRIAGE_WORDS = {
    "why",
    "error",
    "fail",
    "failed",
    "failing",
    "issue",
    "diagnose",
    "diagnosis",
    "triage",
    "crash",
    "crashloop",
    "oom",
    "pending",
    "notready",
    "unhealthy",
    "broken",
    "stuck",
}

_AUDIT_WORDS = {
    "audit",
    "history",
    "who",
    "changed",
    "change",
    "approved",
    "denied",
    "rejected",
    "result",
}

_AUDIT_INTENT_WORDS = {"audit", "history", "who", "changed", "change"}
_ACTION_DENIAL_WORDS = {"denied", "rejected"}
_ACTION_RESULT_WORDS = {"approved", "confirm", "result"}

_ACTION_IMPACTS = {
    "delete_pod": "Kubernetes may recreate it if it is managed by a controller.",
    "exec_pod": "The command will run inside the target pod after approval.",
    "scale_deployment": "This changes the desired replica count for the deployment.",
    "restart_deployment": "This triggers a rolling restart and replaces pods according to the deployment strategy.",
    "rollback_deployment": "This rolls the deployment back to the selected revision.",
    "patch_resource_limits": "This changes container resource requests or limits and may trigger new scheduling behavior.",
    "patch_env_var": "This changes deployment environment configuration and typically triggers a rollout.",
    "scale_statefulset": "This changes StatefulSet replicas and can affect persistent workloads.",
    "restart_statefulset": "This restarts StatefulSet pods sequentially.",
    "restart_daemonset": "This restarts the DaemonSet pod on each matching node.",
    "update_daemonset_image": "This rolls a new image across matching nodes.",
    "delete_job": "This deletes the Job and may delete dependent pods depending on propagation policy.",
    "suspend_job": "This prevents the Job from creating new pods.",
    "resume_job": "This lets the Job create pods again.",
    "suspend_cronjob": "This prevents future scheduled Job runs.",
    "resume_cronjob": "This restores future scheduled Job runs.",
    "delete_service": "This removes the Service endpoint for clients.",
    "delete_configmap": "Pods depending on this ConfigMap may fail or continue with stale mounted data.",
    "delete_secret": "Pods depending on this Secret may fail to start after it is removed.",
    "delete_ingress": "External traffic for the ingress rules will stop routing through this object.",
    "drain_node": "This cordons the node and evicts eligible pods, respecting disruption constraints where possible.",
    "delete_namespace": "This deletes the namespace and all resources inside it.",
    "delete_pvc": "This can permanently remove storage data depending on the reclaim policy.",
}

class StoredMessage(TypedDict):
    """Chat history item passed to the agent graph."""

    role: str
    content: str


@dataclass(frozen=True)
class ActiveAgentResult:
    """Normalized result returned by the active agent graph."""

    text: str
    action: dict[str, Any] | None
    task: str
    tools_called: list[str]
    token_usage: dict[str, int] | None = None
    trace: dict[str, Any] | None = None


_CACHED_ALL_TOOLS: dict[str, list[Any]] = {}
_CACHED_TOOLS_BY_TASK: dict[tuple[str, str], list[Any]] = {}


def classify_task_for_content(content: str, action_context: dict[str, Any] | None = None) -> str:
    """Classify a user message into the smallest useful tool set."""
    text = content.lower()
    words = set(re.findall(r"[a-z_]+", text))

    if action_context:
        if words & _AUDIT_INTENT_WORDS:
            return "audit"
        if words & _ACTION_DENIAL_WORDS:
            return "triage"
        if words & _ACTION_RESULT_WORDS:
            return "inspect"
    if words & _MUTATION_WORDS:
        return "act"
    if words & _TRIAGE_WORDS:
        return "triage"
    if words & _AUDIT_WORDS:
        return "audit"
    return "inspect"


def run_active_agent(
    *,
    content: str,
    history: list[StoredMessage],
    username: str,
    is_god_mode: bool,
    token: str,
    settings: Any,
    action_context: dict[str, Any] | None = None,
) -> ActiveAgentResult:
    """Run the interactive Kubernetes agent through a LangGraph loop."""
    task = classify_task_for_content(content, action_context=action_context)
    tools = _get_tools_cached(task, token=token, debug_mode=bool(settings.debug_mode))

    if not tools:
        raise ValueError(f"No tools returned for task '{task}'")

    llm = _build_llm(settings)
    graph = _build_active_graph(llm, tools)
    messages = _build_messages(
        content=content,
        history=history,
        username=username,
        is_god_mode=is_god_mode,
        task=task,
        action_context=action_context,
    )
    max_iterations = _max_iterations_for_task(task)

    result = graph.invoke(
        {
            "messages": messages,
            "iterations": 0,
            "max_iterations": max_iterations,
            "task": task,
            "tools_called": [],
            "action": None,
        },
        config={"recursion_limit": (max_iterations * 3) + 8},
    )

    final_message = result["messages"][-1]
    assistant_content = getattr(final_message, "content", None)
    if isinstance(assistant_content, str):
        assistant_text = assistant_content
    elif assistant_content is None:
        assistant_text = str(final_message)
    else:
        assistant_text = _json_dumps(assistant_content, max_chars=8000)
    tools_called = result.get("tools_called", [])
    token_usage = _extract_usage(result.get("messages", []))
    trace = {
        "task": task,
        "iterations": int(result.get("iterations", 0)),
        "max_iterations": max_iterations,
        "tools_called": tools_called,
        "action_queued": bool(result.get("action")),
        "token_usage": token_usage,
    }

    return ActiveAgentResult(
        text=_clean_assistant_text(assistant_text),
        action=result.get("action"),
        task=task,
        tools_called=tools_called,
        token_usage=token_usage,
        trace=trace,
    )


def _get_tools_cached(task: str, *, token: str, debug_mode: bool) -> list[Any]:
    """Build tool closures lazily so the app can boot without agent deps installed."""
    from agent.tools import ToolGroup, get_tool_group, get_tools_for_task

    if debug_mode:
        if token in _CACHED_ALL_TOOLS:
            return _CACHED_ALL_TOOLS[token]

        tools: list[Any] = []
        for group in ToolGroup:
            tools.extend(get_tool_group(group, token))
        _CACHED_ALL_TOOLS[token] = tools
        return tools

    key = (task, token)
    if key in _CACHED_TOOLS_BY_TASK:
        return _CACHED_TOOLS_BY_TASK[key]

    tools = get_tools_for_task(task, token)
    _CACHED_TOOLS_BY_TASK[key] = tools
    return tools


def _build_llm(settings: Any) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.agent_model,
        api_key=settings.agent_api_key,
        base_url="https://integrate.api.nvidia.com/v1",
        temperature=0.3,
    )


def _build_active_graph(llm: Any, tools: list[Any]) -> Any:
    from typing import Annotated

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langgraph.graph import END, StateGraph
    from langgraph.graph.message import add_messages

    class ActiveAgentState(TypedDict, total=False):
        messages: Annotated[list[Any], add_messages]
        iterations: int
        max_iterations: int
        task: str
        tools_called: list[str]
        action: dict[str, Any] | None

    tool_map = {tool.name: tool for tool in tools}
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    def call_model(state: ActiveAgentState) -> dict[str, list[Any]]:
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def execute_tools(state: ActiveAgentState) -> dict[str, Any]:
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", []) or []
        tool_messages = []
        tools_called = list(state.get("tools_called", []))
        action = state.get("action")

        for index, call in enumerate(tool_calls):
            name = _tool_call_value(call, "name", "")
            args = _tool_call_value(call, "args", {}) or {}
            call_id = _tool_call_value(call, "id", f"tool_call_{index}")
            tools_called.append(name)

            if action:
                output = {
                    "error": "action_already_pending",
                    "detail": "Skipped because an approval-gated action was already queued.",
                }
            elif name not in tool_map:
                output: Any = {"error": "unknown_tool", "detail": f"Tool '{name}' is not available."}
            else:
                try:
                    output = tool_map[name].invoke(args)
                except Exception as exc:
                    output = {"error": "tool_execution_failed", "detail": str(exc), "tool": name}

            detected_action = _extract_action(output)
            if detected_action:
                action = detected_action

            tool_messages.append(
                ToolMessage(
                    content=_tool_message_content(output),
                    name=name,
                    tool_call_id=str(call_id),
                )
            )

        return {
            "messages": tool_messages,
            "iterations": int(state.get("iterations", 0)) + 1,
            "tools_called": tools_called,
            "action": action,
        }

    def finalize_action(state: ActiveAgentState) -> dict[str, list[Any]]:
        return {"messages": [AIMessage(content=_action_response_text(state.get("action") or {}))]}

    def finalize_max_steps(state: ActiveAgentState) -> dict[str, list[Any]]:
        prompt = (
            "Stop using tools now. Summarize the evidence already gathered, "
            "state what is still uncertain, and give the safest next step. "
            "Do not mention internal graph limits."
        )
        response = llm.invoke([*state["messages"], HumanMessage(content=prompt)])
        return {"messages": [response]}

    def route_after_model(state: ActiveAgentState) -> str:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            if int(state.get("iterations", 0)) >= int(state.get("max_iterations", 4)):
                return "max_steps"
            return "tools"
        return "end"

    def route_after_tools(state: ActiveAgentState) -> str:
        if state.get("action"):
            return "action"
        if int(state.get("iterations", 0)) >= int(state.get("max_iterations", 4)):
            return "max_steps"
        return "agent"

    graph = StateGraph(ActiveAgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", execute_tools)
    graph.add_node("action", finalize_action)
    graph.add_node("max_steps", finalize_max_steps)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        route_after_model,
        {"tools": "tools", "max_steps": "max_steps", "end": END},
    )
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {"agent": "agent", "action": "action", "max_steps": "max_steps"},
    )
    graph.add_edge("action", END)
    graph.add_edge("max_steps", END)
    return graph.compile()


def _build_messages(
    *,
    content: str,
    history: list[StoredMessage],
    username: str,
    is_god_mode: bool,
    task: str,
    action_context: dict[str, Any] | None,
) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    messages: list[Any] = [
        SystemMessage(
            content=_system_prompt(
                username=username,
                is_god_mode=is_god_mode,
                task=task,
                action_context=action_context,
            )
        )
    ]

    for item in history:
        text = item.get("content", "").strip()
        if not text:
            continue
        if item.get("role") == "user":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))

    messages.append(HumanMessage(content=content))
    return messages


def _system_prompt(
    *,
    username: str,
    is_god_mode: bool,
    task: str,
    action_context: dict[str, Any] | None,
) -> str:
    prompt = get_system_instruction(username, is_god_mode=is_god_mode)
    graph_context = f"""

## LANGGRAPH WORKFLOW
You are running inside an explicit LangGraph loop. Work incrementally:
- Start with the most targeted high-signal tool call.
- After each tool result, decide whether another tool will materially improve the answer.
- Stop once you have enough evidence, a missing permission blocks progress, or an approval-gated action request has been created.
- For diagnosis, show concise evidence and options. Do not expose private chain-of-thought or <think> blocks.
- Current task classification: {task}.
"""
    if action_context:
        graph_context += (
            "\n## CURRENT ACTION CONTEXT\n"
            "A recent approval-gated action is relevant to this user turn. "
            "Use this status/result when confirming the outcome:\n"
            f"{_json_dumps(action_context, max_chars=4000)}\n"
        )
    return prompt + graph_context


def _max_iterations_for_task(task: str) -> int:
    if task == "act":
        return 6
    if task == "triage":
        return 6
    if task == "full":
        return 7
    return 4


def _tool_call_value(call: Any, key: str, default: Any = None) -> Any:
    if isinstance(call, dict):
        return call.get(key, default)
    return getattr(call, key, default)


def _tool_message_content(output: Any) -> str:
    if isinstance(output, str):
        return output
    return _json_dumps(output, max_chars=20000)


def _extract_action(output: Any) -> dict[str, Any] | None:
    payload = output
    if isinstance(output, str):
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None
    if not payload.get("id") or not payload.get("type"):
        return None
    if payload.get("status") not in {None, "pending"}:
        return None

    target = payload.get("target")
    return {
        "id": payload["id"],
        "type": payload["type"],
        "target": target if isinstance(target, dict) else {},
    }


def _action_response_text(action: dict[str, Any]) -> str:
    action_type = str(action.get("type") or "action")
    target = action.get("target") if isinstance(action.get("target"), dict) else {}
    name = str(target.get("name") or "the target")
    namespace = str(target.get("namespace") or "default")
    type_label = action_type.replace("_", " ")
    target_label = name if namespace == name else f"{namespace}/{name}"
    impact = _ACTION_IMPACTS.get(
        action_type,
        "The action is pending and has not changed the cluster yet.",
    )

    return (
        f"I've queued {type_label} for {target_label}. {impact}\n\n"
        "Use the options below to approve or deny it. I will wait before taking another action."
    )


def _json_dumps(value: Any, *, max_chars: int) -> str:
    text = json.dumps(value, ensure_ascii=True, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32] + "... [truncated]"


def _clean_assistant_text(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"Action ID:\s*[0-9a-f-]{36}", "", text, flags=re.IGNORECASE).strip()
    return text


def _extract_usage(messages: list[Any]) -> dict[str, int] | None:
    if not messages:
        return None
    last = messages[-1]
    metadata = getattr(last, "response_metadata", None)
    if not isinstance(metadata, dict):
        metadata = getattr(last, "usage_metadata", None)
    if not isinstance(metadata, dict):
        return None

    usage = metadata.get("token_usage") or metadata.get("usage") or metadata
    if not isinstance(usage, dict):
        return None

    def as_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    input_tokens = as_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_tokens_count")
    )
    output_tokens = as_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("completion_tokens_count")
    )
    total_tokens = as_int(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "total_tokens": total_tokens or 0,
    }
