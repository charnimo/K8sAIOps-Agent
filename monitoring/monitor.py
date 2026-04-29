"""
AIOps Platform - Real-Time Kubernetes Monitoring & Notification Subsystem
=========================================================================
Watches Kubernetes cluster resources, processes/enriches events,
routes them to relevant users, and delivers via WebSocket.
"""

import asyncio
import json
import logging
import os
import time
import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol
from aiohttp import web
from kubernetes_asyncio import client, config, watch
from kubernetes_asyncio.client import ApiClient

# ─── Configuration ────────────────────────────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
WS_PORT = int(os.getenv("WS_PORT", "8765"))
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
DEDUP_WINDOW = int(os.getenv("DEDUP_WINDOW_SECONDS", "60"))
MAX_HISTORY = int(os.getenv("MAX_EVENT_HISTORY", "500"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("aiops.monitor")

# ─── Enums & Data Models ──────────────────────────────────────────────────────

class Severity(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    POD_FAILURE      = "POD_FAILURE"
    POD_RESTART      = "POD_RESTART"
    IMAGE_PULL_ERROR = "IMAGE_PULL_ERROR"
    SCHEDULING_ISSUE = "SCHEDULING_ISSUE"
    OOM_KILLED       = "OOM_KILLED"
    NODE_EVENT       = "NODE_EVENT"
    NAMESPACE_EVENT  = "NAMESPACE_EVENT"
    GENERIC_WARNING  = "GENERIC_WARNING"
    GENERIC_INFO     = "GENERIC_INFO"


# Severity classification maps
CRITICAL_REASONS = {
    "CrashLoopBackOff", "OOMKilled", "ImagePullBackOff",
    "ErrImagePull", "NodeNotReady", "Evicted", "FailedKillPod",
}
WARNING_REASONS = {
    "BackOff", "Failed", "FailedScheduling", "FailedMount",
    "Unhealthy", "ProbeWarning", "HostPortConflict", "InsufficientFreeDisk",
    "EvictionThresholdMet", "ContainerGCFailed", "Killing",
}

# Namespace → teams routing table (can be loaded from ConfigMap)
NAMESPACE_TEAM_MAP: dict[str, list[str]] = {
    "production":  ["ops-team", "sre-team"],
    "staging":     ["dev-team", "qa-team"],
    "development": ["dev-team"],
    "kube-system": ["platform-team", "sre-team"],
    "default":     ["ops-team"],
}


@dataclass
class EnrichedEvent:
    """Normalized, enriched Kubernetes event ready for delivery."""
    event_id:       str
    event_type:     EventType
    severity:       Severity
    namespace:      str
    resource_name:  str
    resource_kind:  str
    reason:         str
    message:        str
    timestamp:      str
    node:           Optional[str]
    labels:         dict
    annotations:    dict
    teams:          list[str]          # Routing targets
    raw_count:      int = 1
    first_seen:     Optional[str] = None
    last_seen:      Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["severity"] = self.severity.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# ─── Event Processor ──────────────────────────────────────────────────────────

class EventProcessor:
    """
    Normalises raw Kubernetes objects/events into EnrichedEvents.
    Handles deduplication via a rolling fingerprint cache.
    """

    def __init__(self, dedup_window: int = DEDUP_WINDOW):
        self._dedup_window = dedup_window
        # fingerprint → (EnrichedEvent, expire_time)
        self._dedup_cache: dict[str, tuple[EnrichedEvent, float]] = {}

    # ── Severity classification ──────────────────────────────────────────────

    def _classify_severity(self, reason: str) -> Severity:
        reason_clean = reason.strip()
        if reason_clean in CRITICAL_REASONS:
            return Severity.CRITICAL
        if reason_clean in WARNING_REASONS:
            return Severity.WARNING
        return Severity.INFO

    def _classify_event_type(self, reason: str, resource_kind: str) -> EventType:
        r = reason.strip()
        if r == "CrashLoopBackOff":
            return EventType.POD_FAILURE
        if r in ("ImagePullBackOff", "ErrImagePull"):
            return EventType.IMAGE_PULL_ERROR
        if r == "OOMKilled":
            return EventType.OOM_KILLED
        if r == "FailedScheduling":
            return EventType.SCHEDULING_ISSUE
        if resource_kind == "Node":
            return EventType.NODE_EVENT
        if resource_kind == "Namespace":
            return EventType.NAMESPACE_EVENT
        if r in WARNING_REASONS:
            return EventType.GENERIC_WARNING
        return EventType.GENERIC_INFO

    # ── Routing ─────────────────────────────────────────────────────────────

    def _resolve_teams(
        self,
        namespace: str,
        labels: dict,
        annotations: dict,
    ) -> list[str]:
        """
        Multi-strategy team resolution:
        1. Resource label: team=<name> or owner=<name>
        2. Namespace → team mapping
        3. Fallback: ops-team
        """
        teams: set[str] = set()

        # Strategy 1 – resource labels / annotations
        for key in ("team", "owner", "app.kubernetes.io/team"):
            if labels.get(key):
                teams.add(labels[key])
            if annotations.get(key):
                teams.add(annotations[key])

        # Strategy 2 – namespace mapping
        ns_teams = NAMESPACE_TEAM_MAP.get(namespace, [])
        teams.update(ns_teams)

        # Strategy 3 – fallback
        if not teams:
            teams.add("ops-team")

        return sorted(teams)

    # ── Fingerprint & dedup ──────────────────────────────────────────────────

    def _fingerprint(self, namespace: str, resource_name: str, reason: str) -> str:
        raw = f"{namespace}/{resource_name}/{reason}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _is_duplicate(self, fp: str, event: EnrichedEvent) -> bool:
        """Return True if this fingerprint was seen recently (dedup window)."""
        now = time.monotonic()
        if fp in self._dedup_cache:
            existing_event, expire = self._dedup_cache[fp]
            if now < expire:
                # Update count on existing cached event
                existing_event.raw_count += 1
                existing_event.last_seen = event.timestamp
                return True
        # Cache the new event
        self._dedup_cache[fp] = (event, now + self._dedup_window)
        return False

    def _evict_expired(self):
        now = time.monotonic()
        expired = [fp for fp, (_, exp) in self._dedup_cache.items() if now >= exp]
        for fp in expired:
            del self._dedup_cache[fp]

    # ── Public processors ────────────────────────────────────────────────────

    def from_k8s_event(self, k8s_event: object) -> Optional[EnrichedEvent]:
        """Process a raw Kubernetes Event object."""
        self._evict_expired()
        try:
            obj = k8s_event
            involved = obj.involved_object
            namespace   = obj.metadata.namespace or "default"
            resource    = involved.name or "unknown"
            resource_kind = involved.kind or "Unknown"
            reason      = obj.reason or "Unknown"
            message     = obj.message or ""
            labels      = obj.metadata.labels or {}
            annotations = obj.metadata.annotations or {}
            node        = obj.source.host if obj.source else None
            raw_count   = obj.count or 1
            first_seen  = obj.first_timestamp.isoformat() if obj.first_timestamp else None
            last_seen   = obj.last_timestamp.isoformat() if obj.last_timestamp else None
            timestamp   = last_seen or datetime.now(timezone.utc).isoformat()

            severity   = self._classify_severity(reason)
            event_type = self._classify_event_type(reason, resource_kind)
            teams      = self._resolve_teams(namespace, labels, annotations)

            fp = self._fingerprint(namespace, resource, reason)
            event_id = f"evt-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id,
                event_type=event_type,
                severity=severity,
                namespace=namespace,
                resource_name=resource,
                resource_kind=resource_kind,
                reason=reason,
                message=message,
                timestamp=timestamp,
                node=node,
                labels=dict(labels),
                annotations=dict(annotations),
                teams=teams,
                raw_count=raw_count,
                first_seen=first_seen,
                last_seen=last_seen,
            )

            if self._is_duplicate(fp, enriched):
                log.debug("Deduplicated event %s/%s/%s", namespace, resource, reason)
                return None

            return enriched
        except Exception as exc:
            log.warning("Failed to process k8s event: %s", exc)
            return None

    def from_pod_object(self, pod: object, change_type: str) -> Optional[EnrichedEvent]:
        """Synthesise an event from a Pod watch update (ADDED/MODIFIED/DELETED)."""
        self._evict_expired()
        try:
            meta      = pod.metadata
            namespace = meta.namespace or "default"
            name      = meta.name or "unknown"
            labels    = dict(meta.labels or {})
            annotations = dict(meta.annotations or {})
            status    = pod.status
            phase     = status.phase if status else "Unknown"
            timestamp = datetime.now(timezone.utc).isoformat()

            # Check container statuses for failure reasons
            reason  = "Unknown"
            message = f"Pod {name} phase: {phase}"
            if status and status.container_statuses:
                for cs in status.container_statuses:
                    waiting = cs.state.waiting if cs.state else None
                    terminated = cs.state.terminated if cs.state else None
                    if waiting and waiting.reason in CRITICAL_REASONS | WARNING_REASONS:
                        reason  = waiting.reason
                        message = waiting.message or message
                        break
                    if terminated and terminated.reason in CRITICAL_REASONS | WARNING_REASONS:
                        reason  = terminated.reason
                        message = terminated.message or message
                        break

            if reason == "Unknown" and phase in ("Running", "Pending") and change_type == "ADDED":
                return None   # Normal lifecycle, skip

            severity   = self._classify_severity(reason)
            event_type = self._classify_event_type(reason, "Pod")
            teams      = self._resolve_teams(namespace, labels, annotations)

            fp = self._fingerprint(namespace, name, reason)
            event_id = f"pod-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id,
                event_type=event_type,
                severity=severity,
                namespace=namespace,
                resource_name=name,
                resource_kind="Pod",
                reason=reason,
                message=message,
                timestamp=timestamp,
                node=status.host_ip if status else None,
                labels=labels,
                annotations=annotations,
                teams=teams,
            )

            if self._is_duplicate(fp, enriched):
                return None

            return enriched
        except Exception as exc:
            log.warning("Failed to process pod object: %s", exc)
            return None


# ─── Subscription Registry ────────────────────────────────────────────────────

@dataclass
class Subscription:
    user_id:    str
    namespaces: set[str] = field(default_factory=set)   # empty = all
    teams:      set[str] = field(default_factory=set)   # empty = all
    severities: set[str] = field(default_factory=lambda: {"INFO", "WARNING", "CRITICAL"})
    role:       str = "viewer"   # viewer | operator | admin


class SubscriptionRegistry:
    """Thread-safe registry mapping WebSocket connections → subscriptions."""

    def __init__(self):
        self._subs: dict[WebSocketServerProtocol, Subscription] = {}

    def register(self, ws: WebSocketServerProtocol, sub: Subscription):
        self._subs[ws] = sub
        log.info("Registered user=%s role=%s ns=%s teams=%s",
                 sub.user_id, sub.role, sub.namespaces or "*", sub.teams or "*")

    def unregister(self, ws: WebSocketServerProtocol):
        sub = self._subs.pop(ws, None)
        if sub:
            log.info("Unregistered user=%s", sub.user_id)

    def get_subscribers(self, event: EnrichedEvent) -> list[WebSocketServerProtocol]:
        """Return all connections whose subscription matches this event."""
        targets = []
        for ws, sub in list(self._subs.items()):
            if event.severity.value not in sub.severities:
                continue
            ns_match   = not sub.namespaces or event.namespace in sub.namespaces
            team_match = not sub.teams or bool(set(event.teams) & sub.teams)
            if ns_match and team_match:
                targets.append(ws)
        return targets

    @property
    def connected_count(self) -> int:
        return len(self._subs)

    def summary(self) -> list[dict]:
        return [
            {"user_id": s.user_id, "role": s.role,
             "namespaces": list(s.namespaces), "teams": list(s.teams)}
            for s in self._subs.values()
        ]


# ─── Notification Dispatcher ──────────────────────────────────────────────────

class NotificationDispatcher:
    def __init__(self, registry: SubscriptionRegistry):
        self._registry = registry
        self._history: deque[dict] = deque(maxlen=MAX_HISTORY)

    async def dispatch(self, event: EnrichedEvent):
        """Route an event to all matching subscribers."""
        targets = self._registry.get_subscribers(event)
        if not targets:
            log.debug("No subscribers for event %s (ns=%s teams=%s)",
                      event.event_id, event.namespace, event.teams)
            return

        payload = event.to_json()
        self._history.append(event.to_dict())

        log.info("[%s] %s · %s/%s → %d subscriber(s)",
                 event.severity.value, event.event_type.value,
                 event.namespace, event.resource_name, len(targets))

        await asyncio.gather(
            *[self._send(ws, payload) for ws in targets],
            return_exceptions=True,
        )

    async def _send(self, ws: WebSocketServerProtocol, payload: str):
        try:
            await ws.send(payload)
        except Exception as exc:
            log.warning("Failed to send to client: %s", exc)

    def recent_events(self, limit: int = 50) -> list[dict]:
        return list(self._history)[-limit:]


# ─── Kubernetes Watcher ───────────────────────────────────────────────────────

class KubernetesWatcher:
    def __init__(self, processor: EventProcessor, dispatcher: NotificationDispatcher):
        self._processor  = processor
        self._dispatcher = dispatcher
        self._api_client: Optional[ApiClient] = None

    async def _load_config(self):
        """Load in-cluster config, fall back to kubeconfig for local dev."""
        try:
            config.load_incluster_config()
            log.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            await config.load_kube_config()
            log.info("Loaded local kubeconfig")

    async def start(self):
        await self._load_config()
        self._api_client = ApiClient()
        log.info("Kubernetes watcher started")
        await asyncio.gather(
            self._watch_events(),
            self._watch_pods(),
            self._watch_namespaces(),
        )

    async def _watch_events(self):
        """Watch cluster-wide Kubernetes Events."""
        v1 = client.CoreV1Api(self._api_client)
        w  = watch.Watch()
        log.info("Watching Kubernetes Events …")
        while True:
            try:
                async for raw in w.stream(v1.list_event_for_all_namespaces, timeout_seconds=300):
                    evt_type = raw.get("type")
                    k8s_obj  = raw.get("object")
                    if evt_type in ("ADDED", "MODIFIED") and k8s_obj:
                        enriched = self._processor.from_k8s_event(k8s_obj)
                        if enriched:
                            await self._dispatcher.dispatch(enriched)
            except Exception as exc:
                log.error("Event watch error, restarting: %s", exc)
                await asyncio.sleep(5)

    async def _watch_pods(self):
        """Watch Pod lifecycle changes."""
        v1 = client.CoreV1Api(self._api_client)
        w  = watch.Watch()
        log.info("Watching Pods …")
        while True:
            try:
                async for raw in w.stream(v1.list_pod_for_all_namespaces, timeout_seconds=300):
                    evt_type = raw.get("type")
                    pod      = raw.get("object")
                    if pod and evt_type in ("ADDED", "MODIFIED"):
                        enriched = self._processor.from_pod_object(pod, evt_type)
                        if enriched:
                            await self._dispatcher.dispatch(enriched)
            except Exception as exc:
                log.error("Pod watch error, restarting: %s", exc)
                await asyncio.sleep(5)

    async def _watch_namespaces(self):
        """Watch Namespace changes."""
        v1 = client.CoreV1Api(self._api_client)
        w  = watch.Watch()
        log.info("Watching Namespaces …")
        while True:
            try:
                async for raw in w.stream(v1.list_namespace, timeout_seconds=300):
                    evt_type = raw.get("type")
                    ns_obj   = raw.get("object")
                    if ns_obj and evt_type == "MODIFIED":
                        phase = ns_obj.status.phase if ns_obj.status else "Unknown"
                        if phase == "Terminating":
                            name = ns_obj.metadata.name
                            enriched = EnrichedEvent(
                                event_id=f"ns-{name}-{int(time.time())}",
                                event_type=EventType.NAMESPACE_EVENT,
                                severity=Severity.WARNING,
                                namespace=name,
                                resource_name=name,
                                resource_kind="Namespace",
                                reason="Terminating",
                                message=f"Namespace {name} is being deleted",
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                node=None,
                                labels=dict(ns_obj.metadata.labels or {}),
                                annotations=dict(ns_obj.metadata.annotations or {}),
                                teams=self._processor._resolve_teams(name, {}, {}),
                            )
                            await self._dispatcher.dispatch(enriched)
            except Exception as exc:
                log.error("Namespace watch error, restarting: %s", exc)
                await asyncio.sleep(5)


# ─── WebSocket Server ─────────────────────────────────────────────────────────

class WebSocketServer:
    def __init__(
        self,
        registry: SubscriptionRegistry,
        dispatcher: NotificationDispatcher,
        port: int = WS_PORT,
    ):
        self._registry   = registry
        self._dispatcher = dispatcher
        self._port       = port

    async def handler(self, ws: WebSocketServerProtocol):
        """Handle a new WebSocket connection."""
        log.info("New WS connection from %s", ws.remote_address)
        try:
            # ── Expect subscription handshake ──────────────────────────────
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            sub_data = json.loads(raw)

            sub = Subscription(
                user_id    = sub_data.get("user_id", "anonymous"),
                namespaces = set(sub_data.get("namespaces", [])),
                teams      = set(sub_data.get("teams", [])),
                severities = set(sub_data.get("severities", ["INFO", "WARNING", "CRITICAL"])),
                role       = sub_data.get("role", "viewer"),
            )
            self._registry.register(ws, sub)

            # Send ACK + recent history
            await ws.send(json.dumps({
                "type":    "SUBSCRIBED",
                "user_id": sub.user_id,
                "message": "Subscription active",
                "history": self._dispatcher.recent_events(20),
            }))

            # ── Keep alive: handle ping / subscription updates ─────────────
            async for message in ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "PING":
                        await ws.send(json.dumps({"type": "PONG", "ts": time.time()}))

                    elif msg_type == "UPDATE_SUBSCRIPTION":
                        sub.namespaces = set(data.get("namespaces", []))
                        sub.teams      = set(data.get("teams", []))
                        sub.severities = set(data.get("severities", ["INFO", "WARNING", "CRITICAL"]))
                        await ws.send(json.dumps({"type": "SUBSCRIPTION_UPDATED"}))

                    elif msg_type == "GET_HISTORY":
                        limit = int(data.get("limit", 50))
                        await ws.send(json.dumps({
                            "type":   "HISTORY",
                            "events": self._dispatcher.recent_events(limit),
                        }))
                except json.JSONDecodeError:
                    pass

        except asyncio.TimeoutError:
            log.warning("Client handshake timeout from %s", ws.remote_address)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            log.error("WS handler error: %s", exc)
        finally:
            self._registry.unregister(ws)
            log.info("WS connection closed from %s", ws.remote_address)

    async def start(self):
        log.info("WebSocket server listening on :%d", self._port)
        async with websockets.serve(self.handler, "0.0.0.0", self._port):
            await asyncio.Future()  # run forever


# ─── HTTP Health / Status API ─────────────────────────────────────────────────

class HTTPServer:
    def __init__(
        self,
        registry: SubscriptionRegistry,
        dispatcher: NotificationDispatcher,
        port: int = HTTP_PORT,
    ):
        self._registry   = registry
        self._dispatcher = dispatcher
        self._port       = port
        self._start_time = time.time()

    async def health(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def ready(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ready"})

    async def metrics(self, _: web.Request) -> web.Response:
        return web.json_response({
            "connected_clients": self._registry.connected_count,
            "event_history_size": len(self._dispatcher.recent_events(MAX_HISTORY)),
            "uptime_seconds": int(time.time() - self._start_time),
        })

    async def subscribers(self, _: web.Request) -> web.Response:
        return web.json_response({"subscribers": self._registry.summary()})

    async def recent(self, req: web.Request) -> web.Response:
        limit = int(req.rel_url.query.get("limit", 50))
        return web.json_response({"events": self._dispatcher.recent_events(limit)})

    async def start(self):
        app = web.Application()
        app.router.add_get("/health",      self.health)
        app.router.add_get("/ready",       self.ready)
        app.router.add_get("/metrics",     self.metrics)
        app.router.add_get("/subscribers", self.subscribers)
        app.router.add_get("/events",      self.recent)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()
        log.info("HTTP server listening on :%d", self._port)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

async def main():
    log.info("Starting AIOps Kubernetes Monitor …")

    processor  = EventProcessor(dedup_window=DEDUP_WINDOW)
    registry   = SubscriptionRegistry()
    dispatcher = NotificationDispatcher(registry)

    watcher    = KubernetesWatcher(processor, dispatcher)
    ws_server  = WebSocketServer(registry, dispatcher)
    http_server = HTTPServer(registry, dispatcher)

    await http_server.start()
    await asyncio.gather(
        ws_server.start(),
        watcher.start(),
    )


if __name__ == "__main__":
    asyncio.run(main())
