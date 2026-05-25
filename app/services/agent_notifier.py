from __future__ import annotations

import asyncio
import logging
from typing import Any
import time

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
        # Recent event dedupe map: key -> last_seen_ts
        self._recent_events: dict[str, float] = {}
        # Seconds to suppress duplicate events with same fingerprint/signature
        self._dedupe_window = 120
        # Limit concurrent agent processing (serialize LLM calls)
        self._processing_semaphore = asyncio.Semaphore(1)
        # Cached compiled monitoring graph (built on first use)
        self._compiled_graph = None

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
                # Compute a dedupe key; prefer an explicit fingerprint if present
                try:
                    fingerprint = getattr(event, "dedup_fingerprint", None)
                except Exception:
                    fingerprint = None

                if not fingerprint:
                    try:
                        fingerprint = f"{event.namespace}/{event.resource_name}/{event.reason}"
                    except Exception:
                        fingerprint = getattr(event, "event_id", str(time.time()))

                now = time.time()
                last = self._recent_events.get(fingerprint)
                if last and now - last < self._dedupe_window:
                    log.debug("Suppressing duplicate event for %s (seen %.1fs ago)", fingerprint, now - last)
                    return

                # Record this event as seen
                self._recent_events[fingerprint] = now

                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    log.warning("Agent notification queue full — dropping event %s", getattr(event, "event_id", fingerprint))

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
                # Persist alert and start agent processing in background to avoid blocking the watcher
                try:
                    await self._notify_agent(event)
                except Exception:
                    log.exception("Error while persisting alert for %s", getattr(event, "event_id", None))

                # Kick off processing but don't await here; processing is serialized by semaphore
                asyncio.create_task(self._process_event(event))
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
        # Persist the alert into the shared Auto-Alerts conversation (non-blocking write)
        await handle_agent_event(prompt, event.to_dict(), self._state)

    async def _process_event(self, event):
        """Run the monitoring graph for the given event. Serialized to avoid concurrent LLM calls."""
        try:
            async with self._processing_semaphore:
                # Build/compile the monitoring graph once and cache it
                if self._compiled_graph is None:
                    from app.agent.monitoring_graph import build_monitoring_graph

                    self._compiled_graph = build_monitoring_graph()

                graph = self._compiled_graph

                # Pass the original event object through to the graph to preserve
                # attributes required by Pydantic validation (avoid losing fields
                # by serializing to dict). The graph's `node_extract_event`
                # will accept dicts or `EnrichedEventInput` objects; passing the
                # original event object is the safest option here.
                log.info("Agent processing queued event %s via monitoring graph", getattr(event, "event_id", None))
                try:
                    await graph.ainvoke({"event": event})
                    log.info("Agent processing complete for %s", getattr(event, "event_id", None))
                except Exception as exc:
                    log.error("Agent processing failed for %s: %s", getattr(event, "event_id", None), exc)
        except Exception:
            log.exception("Unexpected error during agent event processing")


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