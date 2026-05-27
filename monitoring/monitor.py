"""
AIOps Platform – Real-Time Kubernetes Monitoring & Notification Subsystem
=========================================================================
Watches Kubernetes cluster resources, processes/enriches events,
routes them to relevant users, and delivers via WebSocket.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import APIRouter, Request
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient, Configuration

# Some kubernetes-asyncio builds reference config.Any from watch.py without
# exporting it from config.__init__.py. Provide the alias before importing watch.
if not hasattr(config, "Any"):
    config.Any = Any
from kubernetes_asyncio import watch


# ─── Configuration (all from env, zero defaults that encode business logic) ───

LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO")
WS_PORT       = int(os.getenv("WS_PORT", "8765"))
HTTP_PORT     = int(os.getenv("HTTP_PORT", "8080"))
DEDUP_WINDOW  = int(os.getenv("DEDUP_WINDOW_SECONDS", "300"))
MAX_HISTORY   = int(os.getenv("MAX_EVENT_HISTORY", "500"))
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("aiops.monitor")


def _configured_api_client() -> ApiClient:
    """Build an ApiClient from the loaded config, including async-client auth fixes."""
    configuration = Configuration.get_default_copy()

    # kubernetes-asyncio can load in-cluster tokens under "authorization" while
    # generated API methods only send auth declared as "BearerToken".
    auth_value = configuration.api_key.get("BearerToken") or configuration.api_key.get("authorization")
    if auth_value:
        if auth_value.lower().startswith("bearer "):
            auth_value = auth_value.split(" ", 1)[1]
        configuration.api_key["BearerToken"] = auth_value
        configuration.api_key_prefix["BearerToken"] = "Bearer"

    return ApiClient(configuration=configuration)


# ─── Enums & Data Models ──────────────────────────────────────────────────────

class Severity(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class EnrichedEvent:
    """
    Normalized, enriched Kubernetes event ready for delivery.

    `reason` carries the Kubernetes-native reason string (e.g. "CrashLoopBackOff",
    "OOMKilled", "FailedScheduling") directly — no synthetic event_type mapping.
    Consumers should branch on `severity` for routing and on `reason` for display/rules.
    """
    event_id:      str
    severity:      Severity
    namespace:     str
    resource_name: str
    resource_kind: str
    reason:        str          # raw Kubernetes reason — source of truth
    message:       str
    timestamp:     str
    node:          Optional[str]
    labels:        dict
    annotations:   dict
    raw_count:     int = 1
    first_seen:    Optional[str] = None
    last_seen:     Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass
class Subscription:
    user_id:    str
    namespaces: set[str] = field(default_factory=set)   # empty = all
    severities: set[str] = field(default_factory=lambda: {"INFO", "WARNING", "CRITICAL"})
    role:       str = "viewer"   # viewer | operator | admin

# ─── Severity / EventType classification (Kubernetes-native) ─────────────────

# Kubernetes only publishes two event types: "Normal" and "Warning".
# We map Warning → WARNING/CRITICAL based on reason semantics, which we
# derive from the Kubernetes source code conventions rather than a fixed set.

# Reasons that indicate immediate / service-affecting failure
_CRITICAL_REASON_PREFIXES = (
    "CrashLoop",
    "OOMKilled",
    "ImagePull",    # ImagePullBackOff, ErrImagePull
    "NodeNotReady",
    "Evicted",
    "FailedKillPod",
    "NodeLost",
    "DiskPressure",
    "MemoryPressure",
    "PIDPressure",
    "NetworkNotReady",
)

_CRITICAL_REASON_EXACT: frozenset[str] = frozenset({
    "BackOff",
    "CrashLoopBackOff",
    "OOMKilled",
    "ImagePullBackOff",
    "ErrImagePull",
    "NodeNotReady",
    "Evicted",
    "FailedKillPod",
})


def _classify_severity(k8s_type: str, reason: str) -> Severity:
    """
    Derive severity from the Kubernetes-native event type + reason.

    - k8s_type == "Normal"  → always INFO (Kubernetes guarantee)
    - k8s_type == "Warning" → CRITICAL if the reason matches a known
                              critical pattern, else WARNING.
    - anything else         → INFO (defensive default)

    This means we never need a hardcoded WARNING set: any Warning event
    that isn't explicitly critical is WARNING by definition.
    """
    if k8s_type != "Warning":
        return Severity.INFO

    r = reason.strip()
    if r in _CRITICAL_REASON_EXACT:
        return Severity.CRITICAL
    for prefix in _CRITICAL_REASON_PREFIXES:
        if r.startswith(prefix):
            return Severity.CRITICAL
    return Severity.WARNING


async def _fetch_permitted_namespaces(token: str) -> list[str] | None:
    """
    Validate token by calling the backend /auth/me endpoint.
    Returns list of namespace strings the user has access to,
    or empty list for god-mode (= all namespaces),
    or None if the token is invalid.
    """
    if not BACKEND_API_URL:
        # no backend configured — open mode, allow all
        log.warning("BACKEND_API_URL not set; skipping auth")
        return []

    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BACKEND_API_URL}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    log.warning("Auth rejected: status %d", resp.status)
                    return None
                body = await resp.json()

        if body.get("is_god_mode"):
            return []  # empty = all namespaces

        perms = body.get("permissions", {})
        namespaces = list(perms.get("namespaces", {}).keys())
        return namespaces

    except Exception as e:
        log.warning("Failed to reach backend for auth: %s", e)
        return None   # fail closed 

# ─── Event Processor ──────────────────────────────────────────────────────────

class EventProcessor:
    """
    Normalises raw Kubernetes objects into EnrichedEvents.
    Deduplicates via rolling fingerprint cache.
    """

    def __init__(
        self,
        dedup_window: int = DEDUP_WINDOW,
    ):
        self._dedup_window = dedup_window
        # fingerprint → (EnrichedEvent, expire_time)
        self._dedup_cache: dict[str, tuple[EnrichedEvent, float]] = {}
        self._seen_timestamp_keys: OrderedDict[tuple[str, str], None] = OrderedDict()

    # ── Fingerprint & dedup ───────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(namespace: str, resource_name: str, reason: str) -> str:
        raw = f"{namespace}/{resource_name}/{reason}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _is_duplicate(self, fp: str, event: EnrichedEvent) -> bool:
        now = time.monotonic()
        if fp in self._dedup_cache:
            existing, expire = self._dedup_cache[fp]
            if now < expire:
                existing.raw_count += 1
                existing.last_seen = event.timestamp
                self._dedup_cache[fp] = (existing, now + self._dedup_window)
                self._remember_event_timestamp(fp, event.timestamp)
                return True

        if event.timestamp and (fp, event.timestamp) in self._seen_timestamp_keys:
            return True

        self._dedup_cache[fp] = (event, now + self._dedup_window)
        self._remember_event_timestamp(fp, event.timestamp)
        return False

    def _remember_event_timestamp(self, fp: str, timestamp: Optional[str]):
        if not timestamp:
            return
        key = (fp, timestamp)
        self._seen_timestamp_keys[key] = None
        self._seen_timestamp_keys.move_to_end(key)
        while len(self._seen_timestamp_keys) > MAX_HISTORY * 8:
            self._seen_timestamp_keys.popitem(last=False)

    def _evict_expired(self):
        now = time.monotonic()
        expired = [fp for fp, (_, exp) in self._dedup_cache.items() if now >= exp]
        for fp in expired:
            del self._dedup_cache[fp]

    # ── Public processors ─────────────────────────────────────────────────────

    def from_k8s_event(self, k8s_event: Any) -> Optional[EnrichedEvent]:
        """Process a raw Kubernetes Event object (kubernetes_asyncio model)."""
        self._evict_expired()
        try:
            obj           = k8s_event
            involved      = obj.involved_object
            namespace     = obj.metadata.namespace or "default"
            resource      = involved.name or "unknown"
            resource_kind = involved.kind or "Unknown"
            reason        = obj.reason or "Unknown"
            k8s_type      = obj.type or "Normal"   # "Normal" | "Warning"
            message       = obj.message or ""
            labels        = dict(obj.metadata.labels or {})
            annotations   = dict(obj.metadata.annotations or {})
            node          = obj.source.host if obj.source else None
            raw_count     = obj.count or 1
            first_seen    = obj.first_timestamp.isoformat() if obj.first_timestamp else None
            last_seen     = obj.last_timestamp.isoformat()  if obj.last_timestamp  else None
            timestamp     = last_seen or datetime.now(timezone.utc).isoformat()

            severity = _classify_severity(k8s_type, reason)

            fp       = self._fingerprint(namespace, resource, reason)
            event_id = f"evt-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id, severity=severity,
                namespace=namespace, resource_name=resource,
                resource_kind=resource_kind, reason=reason, message=message,
                timestamp=timestamp, node=node, labels=labels,
                annotations=annotations,
                raw_count=raw_count, first_seen=first_seen, last_seen=last_seen,
            )

            if self._is_duplicate(fp, enriched):
                log.debug("Deduplicated event %s/%s/%s", namespace, resource, reason)
                return None
            return enriched

        except Exception as exc:
            log.warning("Failed to process k8s event: %s", exc)
            return None

    def from_pod_object(self, pod: Any, change_type: str) -> Optional[EnrichedEvent]:
        """Synthesise an event from a Pod watch update (ADDED/MODIFIED)."""
        self._evict_expired()
        try:
            meta        = pod.metadata
            namespace   = meta.namespace or "default"
            name        = meta.name      or "unknown"
            labels      = dict(meta.labels      or {})
            annotations = dict(meta.annotations or {})
            status      = pod.status
            phase       = status.phase if status else "Unknown"
            timestamp   = datetime.now(timezone.utc).isoformat()

            # Derive reason from container states (Kubernetes-native fields)
            reason  = None
            message = f"Pod {name} phase: {phase}"
            k8s_type = "Normal"

            if status and status.container_statuses:
                for cs in status.container_statuses:
                    waiting    = cs.state.waiting    if cs.state else None
                    terminated = cs.state.terminated if cs.state else None
                    for state in (waiting, terminated):
                        if state and state.reason:
                            # Kubernetes uses Warning-pattern reasons for failures
                            reason   = state.reason
                            message  = state.message or message
                            k8s_type = "Warning"
                            break
                    if reason:
                        break

            if not reason:
                if phase in ("Running", "Pending", "Succeeded") and change_type == "ADDED":
                    return None   # Normal lifecycle
                reason   = f"Phase{phase}"
                k8s_type = "Normal" if phase in ("Running", "Succeeded") else "Warning"

            severity = _classify_severity(k8s_type, reason)

            fp       = self._fingerprint(namespace, name, reason)
            event_id = f"pod-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id, severity=severity,
                namespace=namespace, resource_name=name, resource_kind="Pod",
                reason=reason, message=message, timestamp=timestamp,
                node=pod.spec.node_name if pod.spec else None,
                labels=labels, annotations=annotations,
            )

            if self._is_duplicate(fp, enriched):
                return None
            return enriched

        except Exception as exc:
            log.warning("Failed to process pod object: %s", exc)
            return None

    def synthetic_namespace_event(
        self,
        name: str,
        reason: str,
        message: str,
        labels: dict,
        annotations: dict,
    ) -> EnrichedEvent:
        """Build an EnrichedEvent for a namespace lifecycle change."""
        fp    = self._fingerprint(name, name, reason)
        return EnrichedEvent(
            event_id=f"ns-{fp}-{int(time.time())}",
            severity=Severity.WARNING,
            namespace=name, resource_name=name, resource_kind="Namespace",
            reason=reason, message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            node=None, labels=labels, annotations=annotations,
        )


# ─── Subscription Registry ────────────────────────────────────────────────────

class SubscriptionRegistry:
    """Maps WebSocket connections → Subscriptions."""

    def __init__(self):
        self._subs: dict[WebSocketServerProtocol, Subscription] = {}

    def register(self, ws: WebSocketServerProtocol, sub: Subscription):
        self._subs[ws] = sub
        log.info("Registered user=%s role=%s ns=%s",
                 sub.user_id, sub.role, sub.namespaces or "*")

    def unregister(self, ws: WebSocketServerProtocol):
        sub = self._subs.pop(ws, None)
        if sub:
            log.info("Unregistered user=%s", sub.user_id)

    def get_subscribers(self, event: EnrichedEvent) -> list[WebSocketServerProtocol]:
        targets = []
        for ws, sub in list(self._subs.items()):
            if event.severity.value not in sub.severities:
                continue
            ns_match   = not sub.namespaces or event.namespace in sub.namespaces
            if ns_match:
                targets.append(ws)
        return targets

    @property
    def connected_count(self) -> int:
        return len(self._subs)

    def summary(self) -> list[dict]:
        return [
            {
                "user_id":    s.user_id,
                "role":       s.role,
                "namespaces": list(s.namespaces),
                "severities": list(s.severities),
            }
            for s in self._subs.values()
        ]


# ─── Notification Dispatcher ──────────────────────────────────────────────────

def _event_matches_subscription(event: dict, sub: Subscription) -> bool:
    if event.get("severity") not in sub.severities:
        return False
    return not sub.namespaces or event.get("namespace") in sub.namespaces


class NotificationDispatcher:
    def __init__(self, registry: SubscriptionRegistry):
        self._registry = registry
        self._history: deque[dict] = deque(maxlen=MAX_HISTORY)

    async def dispatch(self, event: EnrichedEvent):
        targets = self._registry.get_subscribers(event)
        self._history.append(event.to_dict())   # always store, even if no live subscribers

        if not targets:
            log.debug("No live subscribers for event %s (ns=%s )",
                      event.event_id, event.namespace)
            return

        payload = event.to_json()
        log.info("[%s] %s · %s/%s → %d subscriber(s)",
                 event.severity.value, event.reason,
                 event.namespace, event.resource_name, len(targets))

        await asyncio.gather(
            *[self._send(ws, payload) for ws in targets],
            return_exceptions=True,
        )

    async def _send(self, ws: WebSocketServerProtocol, payload: str):
        try:
            if hasattr(ws, 'send_text'):
                await ws.send_text(payload)
            else:
                await ws.send(payload)
        except Exception as exc:
            log.warning("Failed to send to client: %s", exc)

    def recent_events(
        self,
        limit: int = 50,
        subscription: Optional[Subscription] = None,
    ) -> list[dict]:
        events = list(self._history)
        if subscription is not None:
            events = [
                event for event in events
                if _event_matches_subscription(event, subscription)
            ]
        return events[-limit:]


# ─── Kubernetes Watcher ───────────────────────────────────────────────────────

class KubernetesWatcher:
    """
    Watches Events, Pods, and Namespaces cluster-wide.
    Delegates enrichment to EventProcessor and delivery to NotificationDispatcher.
    """

    def __init__(
        self,
        processor: EventProcessor,
        dispatcher: NotificationDispatcher,
    ):
        self._processor  = processor
        self._dispatcher = dispatcher
        self._api_client: Optional[ApiClient] = None

    async def _load_config(self):
        try:
            config.load_incluster_config()
            log.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            await config.load_kube_config()
            log.info("Loaded local kubeconfig")

    async def start(self):
        await self._load_config()
        self._api_client = _configured_api_client()
        log.info("Kubernetes watcher started")
        await asyncio.gather(
            self._watch_events(),
            self._watch_pods(),
            self._watch_namespaces(),
        )

    async def _watch_events(self):
        v1 = client.CoreV1Api(self._api_client)
        w  = watch.Watch()
        log.info("Watching Kubernetes Events …")
        while True:
            try:
                async for raw in w.stream(v1.list_event_for_all_namespaces, timeout_seconds=300):
                    if raw.get("type") in ("ADDED", "MODIFIED"):
                        obj = raw.get("object")
                        if obj:
                            enriched = self._processor.from_k8s_event(obj)
                            if enriched:
                                await self._dispatcher.dispatch(enriched)
            except Exception as exc:
                log.error("Event watch error, restarting in 5s: %s", exc)
                await asyncio.sleep(5)

    async def _watch_pods(self):
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
                log.error("Pod watch error, restarting in 5s: %s", exc)
                await asyncio.sleep(5)

    async def _watch_namespaces(self):
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
                            name   = ns_obj.metadata.name
                            labels = dict(ns_obj.metadata.labels or {})
                            annots = dict(ns_obj.metadata.annotations or {})
                            enriched = self._processor.synthetic_namespace_event(
                                name=name,
                                reason="Terminating",
                                message=f"Namespace {name} is being deleted",
                                labels=labels,
                                annotations=annots,
                            )
                            await self._dispatcher.dispatch(enriched)

            except Exception as exc:
                log.error("Namespace watch error, restarting in 5s: %s", exc)
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
        try:
            # ── Step 1: expect AUTH as first message ──────────────────────────
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw)

            if data.get("type") != "AUTH":
                await ws.close(1008, "First message must be AUTH")
                return

            token = data.get("token", "")
            permitted_namespaces = await _fetch_permitted_namespaces(token)

            if permitted_namespaces is None:
                # token was rejected by backend
                await ws.close(1008, "Unauthorized")
                return

            # ── Step 2: build subscription from backend permissions ───────────
            requested_namespaces = set(data.get("namespaces", []))
            allowed_namespaces = set(permitted_namespaces)
            if allowed_namespaces:
                namespaces = (
                    requested_namespaces & allowed_namespaces
                    if requested_namespaces
                    else allowed_namespaces
                )
            else:
                namespaces = requested_namespaces

            sub = Subscription(
                user_id   = data.get("user_id", "unknown"),
                namespaces= namespaces,   # empty set = all
                severities= set(data.get("severities", ["INFO", "WARNING", "CRITICAL"])),
                role      = data.get("role", "viewer"),
            )
            self._registry.register(ws, sub)

            try:
                known_namespaces = await _list_known_namespaces()
                response = {
                    "type":       "SUBSCRIBED",
                    "user_id":    sub.user_id,
                    "message":    "Subscription active",
                    "namespaces":  known_namespaces,
                    "history":    self._dispatcher.recent_events(MAX_HISTORY, sub),
                }
                await ws.send(json.dumps(response, default=str))
            except Exception as exc:
                log.error("Failed to send SUBSCRIBED response: %s", exc)
                raise

            async for message in ws:
                try:
                    data     = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "PING":
                        await ws.send(json.dumps({"type": "PONG", "ts": time.time()}))


                    elif msg_type == "UPDATE_SUBSCRIPTION":
                        requested = set(data.get("namespaces", []))
                        if sub.namespaces:  # non-empty = restricted user, enforce boundary
                            sub.namespaces = requested & sub.namespaces
                        else:
                            sub.namespaces = requested  # god mode, allow anything
                        sub.severities = set(data.get("severities", ["INFO", "WARNING", "CRITICAL"]))
                        await ws.send(json.dumps({"type": "SUBSCRIPTION_UPDATED"}))
                        
                    elif msg_type == "GET_HISTORY":
                        limit = int(data.get("limit", 50))
                        await ws.send(json.dumps({
                            "type":   "HISTORY",
                            "events": self._dispatcher.recent_events(limit, sub),
                        }))

                    elif msg_type == "GET_NAMESPACES":
                        await ws.send(json.dumps({
                            "type": "NAMESPACES",
                            "namespaces": await _list_known_namespaces(),
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
            await asyncio.Future()


# ─── FastAPI integration helpers ──────────────────────────────────────────────
async def build_monitor_components() -> dict:
    """Instantiate and wire all monitor components. Returns a dict of components."""
    processor  = EventProcessor(dedup_window=DEDUP_WINDOW)
    registry   = SubscriptionRegistry()
    dispatcher = NotificationDispatcher(registry)
    watcher    = KubernetesWatcher(processor, dispatcher)
    ws_server  = WebSocketServer(registry, dispatcher)
    return {
        "processor":  processor,
        "registry":   registry,
        "dispatcher": dispatcher,
        "watcher":    watcher,
        "ws_server":  ws_server,
    }


async def _list_known_namespaces(api_client: Optional[ApiClient] = None) -> list[str]:
    """Return namespace names visible to the monitor service."""
    owned_client = False
    if api_client is None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            await config.load_kube_config()
        api_client = _configured_api_client()
        owned_client = True

    try:
        v1 = client.CoreV1Api(api_client)
        response = await v1.list_namespace()
        return sorted(
            item.metadata.name
            for item in response.items
            if item.metadata and item.metadata.name
        )
    except Exception as exc:
        log.warning("Failed to list known namespaces: %s", exc)
        return []
    finally:
        if owned_client:
            await api_client.close()


def get_router():
    """Return a FastAPI APIRouter exposing health/metrics/events/subscribers endpoints."""
    router = APIRouter(prefix="/monitor", tags=["monitor"])

    def _state(request: Request) -> dict:
        return request.app.state.monitor

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    @router.get("/ready")
    async def ready():
        return {"status": "ready"}

    @router.get("/metrics")
    async def metrics(request: Request):
        m = _state(request)
        known_namespaces = await _list_known_namespaces(m["watcher"]._api_client)
        return {
            "connected_clients":  m["registry"].connected_count,
            "event_history_size": len(m["dispatcher"].recent_events(MAX_HISTORY)),
            "known_namespaces": known_namespaces,
        }

    @router.get("/subscribers")
    async def subscribers(request: Request):
        return {"subscribers": _state(request)["registry"].summary()}

    @router.get("/namespaces")
    async def namespaces(request: Request):
        return {"namespaces": await _list_known_namespaces(_state(request)["watcher"]._api_client)}

    @router.get("/events")
    async def events(request: Request, limit: int = 50):
        return {"events": _state(request)["dispatcher"].recent_events(limit)}

    return router


# ─── Standalone entry-point (backwards-compatible) ────────────────────────────

async def _main():
    log.info("Starting AIOps Kubernetes Monitor (standalone) …")
    components  = await build_monitor_components()
    watcher     = components["watcher"]
    ws_server   = components["ws_server"]

    # Minimal HTTP health server (aiohttp) when running standalone
    try:
        from aiohttp import web as aio_web

        async def _health(_):  return aio_web.json_response({"status": "ok"})
        async def _ready(_):   return aio_web.json_response({"status": "ready"})
        async def _metrics(_):
            known_namespaces = await _list_known_namespaces(watcher._api_client)
            return aio_web.json_response({
                "connected_clients":  components["registry"].connected_count,
                "event_history_size": len(components["dispatcher"].recent_events(MAX_HISTORY)),
                "known_namespaces": known_namespaces,
            })
        async def _subscribers(_):
            return aio_web.json_response({"subscribers": components["registry"].summary()})
        async def _namespaces(_):
            return aio_web.json_response({"namespaces": await _list_known_namespaces(watcher._api_client)})
        async def _events(req):
            limit = int(req.rel_url.query.get("limit", 50))
            return aio_web.json_response({"events": components["dispatcher"].recent_events(limit)})

        http_app = aio_web.Application()
        # Support both /health and /monitor/health for backwards compatibility
        http_app.router.add_get("/health",              _health)
        http_app.router.add_get("/monitor/health",      _health)
        http_app.router.add_get("/ready",               _ready)
        http_app.router.add_get("/monitor/ready",       _ready)
        http_app.router.add_get("/metrics",             _metrics)
        http_app.router.add_get("/monitor/metrics",     _metrics)
        http_app.router.add_get("/subscribers",         _subscribers)
        http_app.router.add_get("/monitor/subscribers", _subscribers)
        http_app.router.add_get("/namespaces",          _namespaces)
        http_app.router.add_get("/monitor/namespaces",  _namespaces)
        http_app.router.add_get("/events",              _events)
        http_app.router.add_get("/monitor/events",      _events)

        runner = aio_web.AppRunner(http_app)
        await runner.setup()
        await aio_web.TCPSite(runner, "0.0.0.0", HTTP_PORT).start()
        log.info("HTTP server listening on :%d", HTTP_PORT)
    except ImportError:
        log.warning("aiohttp not installed; HTTP health server disabled in standalone mode")

    await asyncio.gather(ws_server.start(), watcher.start())


if __name__ == "__main__":
    asyncio.run(_main())
