"""
Agent notifier: bridges raw events to the passive AI monitoring graph.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

log = logging.getLogger("aiops.agent_notifier")

def _categorize_reason(reason: str) -> str:
    """
    Map highly specific/cascading K8s reasons into broad failure domains.
    This prevents spam when a controller emits 5 different reason strings 
    for the exact same underlying failure.
    """
    r = reason.lower()
    
    # Order matters! More specific/infrastructural issues should be caught first.
    if any(x in r for x in ["metric", "scale", "replicas", "hpa", "autoscaler"]): 
        return "ScalingFailure"
    if any(x in r for x in ["mount", "volume", "attach", "provision", "storage"]): 
        return "StorageFailure"
    if any(x in r for x in ["schedule", "fit", "affinity", "evict"]): 
        return "SchedulingFailure"
    if any(x in r for x in ["probe", "unhealthy", "health", "readiness", "liveness"]): 
        return "HealthCheckFailure"
    if any(x in r for x in ["image", "pull", "registry"]): 
        return "ImagePullFailure"
    if any(x in r for x in ["oom", "memory"]): 
        return "MemoryFailure"
    if any(x in r for x in ["network", "cni", "sandbox", "dns"]): 
        return "NetworkFailure"
    
    # Catch-all for generic pod/container failures
    if any(x in r for x in ["backoff", "crash", "error", "failed", "exit"]): 
        return "WorkloadCrash"
        
    return reason # Fallback: use raw reason if no category matches


class AgentNotifier:
    AGENT_SEVERITIES = {"WARNING", "CRITICAL"}

    def __init__(self, dispatcher, app_state: Any):
        self._dispatcher = dispatcher
        self._state      = app_state
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._task: asyncio.Task | None = None
        self._recent_events: dict[str, float] = {}
        self._dedupe_window = 300 # 5-minute cooldown
        self._processing_semaphore = asyncio.Semaphore(1)
        self._compiled_graph = None

    def attach(self):
        original_dispatch = self._dispatcher.dispatch

        async def patched_dispatch(event):
            await original_dispatch(event)
            if event.severity.value in self.AGENT_SEVERITIES:
                # Generalized Deduplication: Categorize K8s reasons into broad failure domains
                try:
                    category = _categorize_reason(event.reason)
                    fingerprint = f"{event.namespace}/{event.resource_name}/{category}"
                except Exception:
                    fingerprint = getattr(event, "event_id", str(time.time()))

                now = time.time()
                last = self._recent_events.get(fingerprint)
                if last and now - last < self._dedupe_window:
                    log.debug("Suppressing duplicate event for %s (seen %.1fs ago)", fingerprint, now - last)
                    return

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

    async def _worker(self):
        while True:
            event = await self._queue.get()
            try:
                try:
                    await self._notify_agent(event)
                except Exception:
                    log.exception("Error while persisting alert for %s", getattr(event, "event_id", None))

                asyncio.create_task(self._process_event(event))
            except Exception as exc:
                log.error("Agent notification failed for %s: %s", event.event_id, exc)
            finally:
                self._queue.task_done()

    async def _notify_agent(self, event):
        from app.api.routes.chat import handle_agent_event
        prompt = _build_prompt(event)
        log.info("Notifying agent: [%s] %s/%s (%s)",
                 event.severity.value, event.namespace, event.resource_name, event.reason)
        await handle_agent_event(prompt, event.to_dict(), self._state)

    async def _process_event(self, event):
        try:
            async with self._processing_semaphore:
                if self._compiled_graph is None:
                    from app.agent.monitoring_graph import build_monitoring_graph
                    self._compiled_graph = build_monitoring_graph()

                graph = self._compiled_graph
                log.info("Agent processing queued event %s via monitoring graph", getattr(event, "event_id", None))
                try:
                    result = await graph.ainvoke({"event": event})
                    log.info("Agent processing complete for %s", getattr(event, "event_id", None))
                    
                    # Live push to UI WebSocket
                    incident = result.get("incident_record")
                    if incident:
                        payload = {
                            "type": "INCIDENT_LIVE",
                            "incident_id": incident.incident_id,
                            "resource_type": incident.resource_type,
                            "resource_name": incident.resource_name,
                            "namespace": incident.namespace,
                            "reason": incident.reason,
                            "severity": incident.severity,
                            "summary": incident.summary,
                            "detailed_summary": incident.detailed_summary,
                            "status": incident.status,
                            "created_at": incident.created_at.isoformat() if incident.created_at else None,
                            "root_cause_analysis": incident.root_cause_analysis.dict() if hasattr(incident.root_cause_analysis, "dict") else incident.root_cause_analysis,
                        }
                        
                        targets = self._dispatcher._registry._subs.keys()
                        import json
                        raw_payload = json.dumps(payload, default=str)
                        for ws in list(targets):
                            try:
                                if hasattr(ws, 'send_text'):
                                    await ws.send_text(raw_payload)
                                else:
                                    await ws.send(raw_payload)
                            except Exception:
                                pass
                except Exception as exc:
                    log.error("Agent processing failed for %s: %s", getattr(event, "event_id", None), exc)
        except Exception:
            log.exception("Unexpected error during agent event processing")

def _build_prompt(event) -> str:
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
