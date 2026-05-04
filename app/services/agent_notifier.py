from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("aiops.agent_notifier")


class AgentNotifier:
    """
    Attaches to a NotificationDispatcher as a second dispatch sink.
    Converts EnrichedEvents into agent prompts and queues them
    for async processing — fire-and-forget, never blocks the watcher.
    """

    # Only auto-escalate these severities, INFO is noise for the agent
    AGENT_SEVERITIES = {"WARNING", "CRITICAL"}

    def __init__(self, dispatcher, app_state: Any):
        self._dispatcher = dispatcher
        self._state      = app_state # FastAPI app.state
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def attach(self):
        """
        Monkey-patch the dispatcher's dispatch method to also
        notify the agent. Call once during lifespan startup.
        """
        original_dispatch = self._dispatcher.dispatch

        async def patched_dispatch(event):
            await original_dispatch(event)
            if event.severity.value in self.AGENT_SEVERITIES:
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    log.warning("Agent notification queue full — dropping event %s", event.event_id)

        self._dispatcher.dispatch = patched_dispatch
        self._task = asyncio.create_task(self._worker())
        log.info("AgentNotifier attached to dispatcher")

    def detach(self):
        if self._task:
            self._task.cancel()

    # ── Worker ────────────────────────────────────────────────────────────────

    async def _worker(self):
        """Drains the queue and calls the agent for each event."""
        while True:
            event = await self._queue.get()
            try:
                await self._notify_agent(event)
            except Exception as exc:
                log.error("Agent notification failed for %s: %s", event.event_id, exc)
            finally:
                self._queue.task_done()

    async def _notify_agent(self, event):
        """
        Build a minimal context prompt and send it to the agent chat endpoint.
        The agent decides what to do — this side never hardcodes actions.
        """
        from app.api.routes.chat import handle_agent_event  # late import avoids circular

        prompt = _build_prompt(event)
        log.info("Notifying agent: [%s] %s/%s (%s)",
                 event.severity.value, event.namespace, event.resource_name, event.reason)
        await handle_agent_event(prompt, event.to_dict(), self._state)


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(event) -> str:
    """
    Compact, structured prompt. The agent already has tool access to
    events.py, pods.py, etc. — so this is a trigger, not a full briefing.
    """
    lines = [
        f"[AUTO-ALERT] Severity: {event.severity.value}",
        f"Namespace: {event.namespace} | Resource: {event.resource_kind}/{event.resource_name}",
        f"Reason: {event.reason}",
        f"Message: {event.message}",
    ]
    if event.node:
        lines.append(f"Node: {event.node}")
    if event.raw_count > 1:
        lines.append(f"Occurred {event.raw_count}x (first: {event.first_seen}, last: {event.last_seen})")
    lines.append(
        "Investigate using your available tools and take appropriate action or surface a recommendation."
    )
    return "\n".join(lines)