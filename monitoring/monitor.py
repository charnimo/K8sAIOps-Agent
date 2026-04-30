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
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import websockets
from websockets.server import WebSocketServerProtocol
from kubernetes_asyncio import client, config, watch
from kubernetes_asyncio.client import ApiClient

from Tools.teams import extract_teams


# ─── Configuration (all from env, zero defaults that encode business logic) ───

LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO")
WS_PORT       = int(os.getenv("WS_PORT", "8765"))
HTTP_PORT     = int(os.getenv("HTTP_PORT", "8080"))
DEDUP_WINDOW  = int(os.getenv("DEDUP_WINDOW_SECONDS", "60"))
MAX_HISTORY   = int(os.getenv("MAX_EVENT_HISTORY", "500"))
# How often (seconds) to refresh the namespace→team cache from the cluster
NS_CACHE_TTL  = int(os.getenv("NS_CACHE_TTL_SECONDS", "120"))
# Fallback team when no label/annotation/namespace-mapping resolves a team
FALLBACK_TEAM = os.getenv("FALLBACK_TEAM", "ops-team")

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
    teams:         list[str]
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
    teams:      set[str] = field(default_factory=set)   # empty = all
    severities: set[str] = field(default_factory=lambda: {"INFO", "WARNING", "CRITICAL"})
    role:       str = "viewer"   # viewer | operator | admin


# ─── Dynamic Namespace / Team Cache ──────────────────────────────────────────

class NamespaceTeamCache:
    """
    Maintains a live namespace → [teams] mapping discovered from the cluster.

    Team resolution order (per namespace):
      1. Namespace label/annotation  team=<x>  owner=<x>  app.kubernetes.io/team=<x>
      2. tools.namespaces.get_namespace_teams(name)  (if the tool is available)
      3. FALLBACK_TEAM env var

    The cache is refreshed every NS_CACHE_TTL seconds in the background.
    It is also available synchronously (returns a stale snapshot while
    refresh is in progress) so EventProcessor never blocks.
    """

    def __init__(self):
        self._map: dict[str, list[str]] = {}
        self._namespaces: list[str] = []
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def teams_for(self, namespace: str) -> list[str]:
        """Return known teams for a namespace (may be stale)."""
        return list(self._map.get(namespace, [FALLBACK_TEAM]))

    def known_namespaces(self) -> list[str]:
        return list(self._namespaces)

    async def refresh(self, api_client: Optional[ApiClient] = None):
        """Discover all namespaces and their owning teams from the cluster."""
        async with self._lock:
            try:
                namespaces = await self._list_namespaces(api_client)
                new_map: dict[str, list[str]] = {}
                for ns in namespaces:
                    teams = self._extract_teams_from_metadata(
                        ns.get("labels", {}),
                        ns.get("annotations", {}),
                    )
                    # Try the tools layer if no team resolved from metadata
                    if not teams:
                        teams = await self._tools_teams(ns["name"])
                    if not teams:
                        teams = [FALLBACK_TEAM]
                    new_map[ns["name"]] = sorted(set(teams))

                self._map = new_map
                self._namespaces = [ns["name"] for ns in namespaces]
                self._last_refresh = time.monotonic()
                log.info("Namespace cache refreshed: %d namespaces", len(self._namespaces))
            except Exception as exc:
                log.warning("Namespace cache refresh failed: %s", exc)

    async def start_background_refresh(self, api_client: Optional[ApiClient] = None):
        """Run periodic refresh forever (call with asyncio.create_task)."""
        while True:
            await self.refresh(api_client)
            await asyncio.sleep(NS_CACHE_TTL)

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _list_namespaces(api_client: Optional[ApiClient]) -> list[dict]:
        """
        Try tools.namespaces.list_namespaces() first; fall back to direct API.
        Returns list of dicts: {name, labels, annotations}
        """
        try:
            from Tools.namespaces import list_namespaces  # type: ignore
            raw = list_namespaces()
            return [
                {
                    "name":        ns.get("name", ""),
                    "labels":      ns.get("labels", {}) or {},
                    "annotations": ns.get("annotations", {}) or {},
                }
                for ns in raw
                if ns.get("name")
            ]
        except ImportError:
            pass
        except Exception as exc:
            log.debug("tools.namespaces.list_namespaces failed: %s", exc)

        # # Direct Kubernetes API fallback
        # v1 = client.CoreV1Api(api_client)
        # ns_list = await v1.list_namespace()
        # return [
        #     {
        #         "name":        ns.metadata.name,
        #         "labels":      dict(ns.metadata.labels or {}),
        #         "annotations": dict(ns.metadata.annotations or {}),
        #     }
        #     for ns in ns_list.items
        # ]

    @staticmethod
    async def _tools_teams(namespace: str) -> list[str]:
        try:
            from Tools.namespaces import get_namespace_teams
            return get_namespace_teams(namespace) or []
        except (ImportError, Exception):
            return []

    @staticmethod
    def _extract_teams_from_metadata(labels: dict, annotations: dict) -> list[str]:
        return extract_teams(labels, annotations)


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



# ─── Event Processor ──────────────────────────────────────────────────────────

class EventProcessor:
    """
    Normalises raw Kubernetes objects into EnrichedEvents.
    Deduplicates via rolling fingerprint cache.
    Uses NamespaceTeamCache for dynamic team routing.
    """

    def __init__(
        self,
        ns_cache: NamespaceTeamCache,
        dedup_window: int = DEDUP_WINDOW,
    ):
        self._ns_cache     = ns_cache
        self._dedup_window = dedup_window
        # fingerprint → (EnrichedEvent, expire_time)
        self._dedup_cache: dict[str, tuple[EnrichedEvent, float]] = {}

    # ── Routing ──────────────────────────────────────────────────────────────

    def _resolve_teams(
        self,
        namespace: str,
        labels: dict,
        annotations: dict,
    ) -> list[str]:
        """
        Multi-strategy team resolution:
          1. Resource label / annotation (team, owner, app.kubernetes.io/team, …)
          2. Namespace → team mapping from NamespaceTeamCache
          3. FALLBACK_TEAM
        """
        teams: set[str] = set()

        # Strategy 1 – resource metadata
        teams.update(extract_teams(labels, annotations))

        # Strategy 2 – namespace-level mapping
        teams.update(self._ns_cache.teams_for(namespace))

        # Strategy 3 – fallback (ns_cache already inserts FALLBACK_TEAM
        # when nothing else resolves, but guard here too)
        if not teams:
            teams.add(FALLBACK_TEAM)

        return sorted(teams)

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
                return True
        self._dedup_cache[fp] = (event, now + self._dedup_window)
        return False

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
            teams    = self._resolve_teams(namespace, labels, annotations)

            fp       = self._fingerprint(namespace, resource, reason)
            event_id = f"evt-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id, severity=severity,
                namespace=namespace, resource_name=resource,
                resource_kind=resource_kind, reason=reason, message=message,
                timestamp=timestamp, node=node, labels=labels,
                annotations=annotations, teams=teams,
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
            teams    = self._resolve_teams(namespace, labels, annotations)

            fp       = self._fingerprint(namespace, name, reason)
            event_id = f"pod-{fp}-{int(time.time())}"

            enriched = EnrichedEvent(
                event_id=event_id, severity=severity,
                namespace=namespace, resource_name=name, resource_kind="Pod",
                reason=reason, message=message, timestamp=timestamp,
                node=status.host_ip if status else None,
                labels=labels, annotations=annotations, teams=teams,
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
        teams = self._resolve_teams(name, labels, annotations)
        fp    = self._fingerprint(name, name, reason)
        return EnrichedEvent(
            event_id=f"ns-{fp}-{int(time.time())}",
            severity=Severity.WARNING,
            namespace=name, resource_name=name, resource_kind="Namespace",
            reason=reason, message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            node=None, labels=labels, annotations=annotations, teams=teams,
        )


# ─── Subscription Registry ────────────────────────────────────────────────────

class SubscriptionRegistry:
    """Maps WebSocket connections → Subscriptions."""

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
        targets = []
        for ws, sub in list(self._subs.items()):
            if event.severity.value not in sub.severities:
                continue
            ns_match   = not sub.namespaces or event.namespace in sub.namespaces
            team_match = not sub.teams      or bool(set(event.teams) & sub.teams)
            if ns_match and team_match:
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
                "teams":      list(s.teams),
                "severities": list(s.severities),
            }
            for s in self._subs.values()
        ]


# ─── Notification Dispatcher ──────────────────────────────────────────────────

class NotificationDispatcher:
    def __init__(self, registry: SubscriptionRegistry):
        self._registry = registry
        self._history: deque[dict] = deque(maxlen=MAX_HISTORY)

    async def dispatch(self, event: EnrichedEvent):
        targets = self._registry.get_subscribers(event)
        self._history.append(event.to_dict())   # always store, even if no live subscribers

        if not targets:
            log.debug("No live subscribers for event %s (ns=%s teams=%s)",
                      event.event_id, event.namespace, event.teams)
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
            await ws.send(payload)
        except Exception as exc:
            log.warning("Failed to send to client: %s", exc)

    def recent_events(self, limit: int = 50) -> list[dict]:
        return list(self._history)[-limit:]


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
        ns_cache: NamespaceTeamCache,
    ):
        self._processor  = processor
        self._dispatcher = dispatcher
        self._ns_cache   = ns_cache
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
        self._api_client = ApiClient()
        log.info("Kubernetes watcher started")
        # Initial namespace cache warm-up before watches begin
        await self._ns_cache.refresh(self._api_client)
        await asyncio.gather(
            self._watch_events(),
            self._watch_pods(),
            self._watch_namespaces(),
            self._ns_cache.start_background_refresh(self._api_client),
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
                            # Also invalidate cache so the deleted ns is removed on next refresh
                            await self._ns_cache.refresh(self._api_client)
            except Exception as exc:
                log.error("Namespace watch error, restarting in 5s: %s", exc)
                await asyncio.sleep(5)


# ─── WebSocket Server ─────────────────────────────────────────────────────────

class WebSocketServer:
    def __init__(
        self,
        registry: SubscriptionRegistry,
        dispatcher: NotificationDispatcher,
        ns_cache: NamespaceTeamCache,
        port: int = WS_PORT,
    ):
        self._registry   = registry
        self._dispatcher = dispatcher
        self._ns_cache   = ns_cache
        self._port       = port

    async def handler(self, ws: WebSocketServerProtocol):
        log.info("New WS connection from %s", ws.remote_address)
        try:
            raw      = await asyncio.wait_for(ws.recv(), timeout=10.0)
            sub_data = json.loads(raw)

            sub = Subscription(
                user_id    = sub_data.get("user_id", "anonymous"),
                namespaces = set(sub_data.get("namespaces", [])),
                teams      = set(sub_data.get("teams", [])),
                severities = set(sub_data.get("severities", ["INFO", "WARNING", "CRITICAL"])),
                role       = sub_data.get("role", "viewer"),
            )
            self._registry.register(ws, sub)

            try:
                response = {
                    "type":       "SUBSCRIBED",
                    "user_id":    sub.user_id,
                    "message":    "Subscription active",
                    "history":    self._dispatcher.recent_events(20),
                    # Send live namespace / team catalog so the client can populate filters
                    "namespaces": self._ns_cache.known_namespaces(),
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

                    elif msg_type == "GET_NAMESPACES":
                        await ws.send(json.dumps({
                            "type":       "NAMESPACES",
                            "namespaces": self._ns_cache.known_namespaces(),
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
#
# Usage in your FastAPI app:
#
#   from monitor import build_monitor_components, get_router
#
#   @asynccontextmanager
#   async def lifespan(app: FastAPI):
#       components = await build_monitor_components()
#       app.state.monitor = components
#       task = asyncio.create_task(components["watcher"].start())
#       yield
#       task.cancel()
#
#   app = FastAPI(lifespan=lifespan)
#   app.include_router(get_router())

async def build_monitor_components() -> dict:
    """Instantiate and wire all monitor components. Returns a dict of components."""
    ns_cache   = NamespaceTeamCache()
    processor  = EventProcessor(ns_cache, dedup_window=DEDUP_WINDOW)
    registry   = SubscriptionRegistry()
    dispatcher = NotificationDispatcher(registry)
    watcher    = KubernetesWatcher(processor, dispatcher, ns_cache)
    ws_server  = WebSocketServer(registry, dispatcher, ns_cache)
    return {
        "ns_cache":   ns_cache,
        "processor":  processor,
        "registry":   registry,
        "dispatcher": dispatcher,
        "watcher":    watcher,
        "ws_server":  ws_server,
    }


def get_router():
    """Return a FastAPI APIRouter exposing health/metrics/events/subscribers endpoints."""
    try:
        from fastapi import APIRouter, Request
        from fastapi.responses import JSONResponse
    except ImportError:
        raise RuntimeError("fastapi is not installed; install it to use get_router()")

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
        return {
            "connected_clients":  m["registry"].connected_count,
            "event_history_size": len(m["dispatcher"].recent_events(MAX_HISTORY)),
            "known_namespaces":   len(m["ns_cache"].known_namespaces()),
        }

    @router.get("/subscribers")
    async def subscribers(request: Request):
        return {"subscribers": _state(request)["registry"].summary()}

    @router.get("/events")
    async def events(request: Request, limit: int = 50):
        return {"events": _state(request)["dispatcher"].recent_events(limit)}

    @router.get("/namespaces")
    async def namespaces(request: Request):
        return {"namespaces": _state(request)["ns_cache"].known_namespaces()}

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
            return aio_web.json_response({
                "connected_clients":  components["registry"].connected_count,
                "event_history_size": len(components["dispatcher"].recent_events(MAX_HISTORY)),
                "known_namespaces":   len(components["ns_cache"].known_namespaces()),
            })
        async def _subscribers(_):
            return aio_web.json_response({"subscribers": components["registry"].summary()})
        async def _events(req):
            limit = int(req.rel_url.query.get("limit", 50))
            return aio_web.json_response({"events": components["dispatcher"].recent_events(limit)})
        async def _namespaces(_):
            return aio_web.json_response({"namespaces": components["ns_cache"].known_namespaces()})

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
        http_app.router.add_get("/events",              _events)
        http_app.router.add_get("/monitor/events",      _events)
        http_app.router.add_get("/namespaces",          _namespaces)
        http_app.router.add_get("/monitor/namespaces",  _namespaces)

        runner = aio_web.AppRunner(http_app)
        await runner.setup()
        await aio_web.TCPSite(runner, "0.0.0.0", HTTP_PORT).start()
        log.info("HTTP server listening on :%d", HTTP_PORT)
    except ImportError:
        log.warning("aiohttp not installed; HTTP health server disabled in standalone mode")

    await asyncio.gather(ws_server.start(), watcher.start())


if __name__ == "__main__":
    asyncio.run(_main())