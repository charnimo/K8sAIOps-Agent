"""
Integration tests for:
  - WebSocket subscription + event delivery (monitor.py)
  - AgentNotifier push (agent_notifier.py)
  - handle_agent_event DB persistence (chat.py)

PRE-REQUISITES
──────────────
  minikube start
  kubectl apply -f manifests/monitoring/rbac.yaml
  kubectl apply -f manifests/monitoring/deployment.yaml
  kubectl apply -f manifests/test-workloads.yaml

  # Forward the monitor ports locally
  kubectl -n aiops-system port-forward svc/aiops-monitor-svc 8765:8765 8080:8080

  # Run
  pip install websockets httpx pytest pytest-asyncio
  pytest tests/test_monitor_integration.py -v

ENV OVERRIDES (optional)
────────────────────────
  MONITOR_WS_URL   default: ws://localhost:8765
  MONITOR_HTTP_URL default: http://localhost:8080
  EVENT_WAIT_SEC   default: 90   (how long to wait for events to arrive)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
import websockets

# ── Config ────────────────────────────────────────────────────────────────────

WS_URL        = os.getenv("MONITOR_WS_URL",   "ws://localhost:8765")
HTTP_URL      = os.getenv("MONITOR_HTTP_URL", "http://localhost:8080")
EVENT_WAIT    = int(os.getenv("EVENT_WAIT_SEC", "90"))
AUTH_TOKEN    = os.getenv("MONITOR_AUTH_TOKEN", "")


def _monitor_is_reachable() -> bool:
    """Return whether live monitor endpoints are available for integration tests."""
    try:
        response = httpx.get(f"{HTTP_URL}/monitor/health", timeout=1)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


_LIVE_MONITOR_AVAILABLE = _monitor_is_reachable()
_requires_live_monitor = pytest.mark.skipif(
    not _LIVE_MONITOR_AVAILABLE,
    reason=(
        "live monitor is not reachable; start the monitoring deployment and "
        "port-forward MONITOR_HTTP_URL/MONITOR_WS_URL to run these integration tests"
    ),
)


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

async def _collect_events(
    duration: float,
    subscription: Optional[dict] = None,
) -> list[dict]:
    """
    Open a WebSocket, subscribe, and collect all events for `duration` seconds.
    Returns list of EnrichedEvent dicts (excludes control frames like SUBSCRIBED/PONG).
    """
    sub = subscription or {
        "user_id":    "test-runner",
        "severities": ["INFO", "WARNING", "CRITICAL"],
        "namespaces": [],   # empty = all
        "role":       "admin",
    }
    auth_message = {
        "type": "AUTH",
        "token": AUTH_TOKEN,
        **sub,
    }
    events: list[dict] = []
    deadline = time.monotonic() + duration

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps(auth_message))

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 2.0))
                data = json.loads(raw)
                # Handle SUBSCRIBED frame - extract history
                if data.get("type") == "SUBSCRIBED":
                    history = data.get("history", [])
                    for evt in history:
                        if "event_id" in evt:
                            events.append(evt)
                    continue
                # Skip other control frames
                if data.get("type") in ("PONG", "SUBSCRIPTION_UPDATED",
                                         "HISTORY", "NAMESPACES"):
                    continue
                # Real events have event_id
                if "event_id" in data:
                    events.append(data)
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break

    return events


def _find(events: list[dict], **filters) -> list[dict]:
    """Filter events by any field values."""
    result = []
    for ev in events:
        if all(ev.get(k) == v for k, v in filters.items()):
            result.append(ev)
    return result


class TestEventProcessorDedup:
    """Regression coverage for monitor-side Kubernetes event deduplication."""

    def _k8s_event(self, timestamp: datetime) -> SimpleNamespace:
        return SimpleNamespace(
            metadata=SimpleNamespace(namespace="default", labels={}, annotations={}),
            involved_object=SimpleNamespace(name="demo-pod", kind="Pod"),
            reason="Started",
            type="Normal",
            message="Started container",
            source=SimpleNamespace(host="minikube"),
            count=1,
            first_timestamp=timestamp,
            last_timestamp=timestamp,
        )

    def test_replayed_event_timestamp_is_suppressed_after_window(self):
        from monitoring.monitor import EventProcessor

        processor = EventProcessor(dedup_window=1)
        first_event = self._k8s_event(datetime(2026, 5, 27, 18, 0, tzinfo=timezone.utc))
        later_event = self._k8s_event(datetime(2026, 5, 27, 18, 5, tzinfo=timezone.utc))

        first = processor.from_k8s_event(first_event)
        assert first is not None

        fp = processor._fingerprint("default", "demo-pod", "Started")
        cached_event, _ = processor._dedup_cache[fp]
        processor._dedup_cache[fp] = (cached_event, time.monotonic() - 1)

        later = processor.from_k8s_event(later_event)
        assert later is not None

        cached_event, _ = processor._dedup_cache[fp]
        processor._dedup_cache[fp] = (cached_event, time.monotonic() - 1)

        assert processor.from_k8s_event(first_event) is None


@pytest.mark.asyncio
async def test_dispatcher_suppresses_duplicate_delivery_and_history():
    from monitoring.monitor import EnrichedEvent, NotificationDispatcher, Severity, Subscription, SubscriptionRegistry

    sent_payloads = []

    class FakeWebSocket:
        async def send(self, payload: str):
            sent_payloads.append(json.loads(payload))

    registry = SubscriptionRegistry()
    ws = FakeWebSocket()
    registry.register(
        ws,
        Subscription(
            user_id="dedup-test",
            namespaces=set(),
            severities={"INFO", "WARNING", "CRITICAL"},
            role="admin",
        ),
    )
    dispatcher = NotificationDispatcher(registry, dedup_window=300)

    first = EnrichedEvent(
        event_id="evt-1",
        severity=Severity.CRITICAL,
        namespace="default",
        resource_name="crashloop-test",
        resource_kind="Pod",
        reason="CrashLoopBackOff",
        message="first",
        timestamp="2026-05-27T18:00:00+00:00",
        node="minikube",
        labels={},
        annotations={},
        raw_count=1,
    )
    duplicate = EnrichedEvent(
        event_id="evt-2",
        severity=Severity.CRITICAL,
        namespace="default",
        resource_name="crashloop-test",
        resource_kind="Pod",
        reason="CrashLoopBackOff",
        message="second",
        timestamp="2026-05-27T18:00:05+00:00",
        node="minikube",
        labels={},
        annotations={},
        raw_count=2,
    )

    assert await dispatcher.dispatch(first) is True
    assert await dispatcher.dispatch(duplicate) is False

    history = dispatcher.recent_events(10)
    assert len(history) == 1
    assert history[0]["raw_count"] == 3
    assert history[0]["message"] == "second"
    assert len(sent_payloads) == 1
    assert sent_payloads[0]["event_id"] == "evt-1"


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 – HTTP health checks  (fast, no waiting)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@_requires_live_monitor
class TestHTTPEndpoints:
    """Verify the monitor's REST API is reachable and returns valid data."""

    def test_health(self):
        r = httpx.get(f"{HTTP_URL}/monitor/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_ready(self):
        r = httpx.get(f"{HTTP_URL}/monitor/ready", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_metrics_shape(self):
        r = httpx.get(f"{HTTP_URL}/monitor/metrics", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert "connected_clients"  in body
        assert "event_history_size" in body
        assert "known_namespaces"   in body

    def test_namespaces_includes_default(self):
        r = httpx.get(f"{HTTP_URL}/monitor/namespaces", timeout=5)
        assert r.status_code == 200
        ns = r.json()["namespaces"]
        assert isinstance(ns, list)
        assert "default" in ns

    def test_events_endpoint(self):
        r = httpx.get(f"{HTTP_URL}/monitor/events?limit=10", timeout=5)
        assert r.status_code == 200
        assert "events" in r.json()


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 – WebSocket protocol
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.asyncio
@_requires_live_monitor
class TestWebSocketProtocol:

    async def test_subscribed_frame_on_connect(self):
        """Monitor must respond with SUBSCRIBED immediately after handshake."""
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({
                "type": "AUTH",
                "token": AUTH_TOKEN,
                "user_id": "proto-test",
                "severities": ["CRITICAL"],
            }))
            raw  = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw)

        assert data["type"] == "SUBSCRIBED"
        assert data["user_id"] == "proto-test"
        assert "namespaces" in data       # catalog sent on connect
        assert "history"    in data       # recent events included

    async def test_ping_pong(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "AUTH", "token": AUTH_TOKEN, "user_id": "ping-test", "severities": ["INFO"]}))
            await ws.recv()   # SUBSCRIBED

            await ws.send(json.dumps({"type": "PING"}))
            raw  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)

        assert data["type"] == "PONG"
        assert "ts" in data

    async def test_get_history(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "AUTH", "token": AUTH_TOKEN, "user_id": "history-test", "severities": ["INFO", "WARNING", "CRITICAL"]}))
            await ws.recv()   # SUBSCRIBED

            await ws.send(json.dumps({"type": "GET_HISTORY", "limit": 5}))
            raw  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)

        assert data["type"] == "HISTORY"
        assert isinstance(data["events"], list)

    async def test_update_subscription(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "AUTH", "token": AUTH_TOKEN, "user_id": "update-test", "severities": ["INFO"]}))
            await ws.recv()

            await ws.send(json.dumps({
                "type":       "UPDATE_SUBSCRIPTION",
                "severities": ["CRITICAL"],
                "namespaces": ["default"],
            }))
            raw  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)

        assert data["type"] == "SUBSCRIPTION_UPDATED"

    async def test_get_namespaces(self):
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"type": "AUTH", "token": AUTH_TOKEN, "user_id": "ns-test", "severities": ["INFO"]}))
            await ws.recv()

            await ws.send(json.dumps({"type": "GET_NAMESPACES"}))
            raw  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)

        assert data["type"] == "NAMESPACES"
        assert "default" in data["namespaces"]

    async def test_handshake_timeout_on_no_subscription(self):
        """Monitor should close the connection if no subscription arrives in 10 s."""
        async with websockets.connect(WS_URL) as ws:
            try:
                # Send nothing — wait for server to close
                await asyncio.wait_for(ws.recv(), timeout=15)
            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
                pass   # expected


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 – Real event delivery from test-workloads.yaml
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@_requires_live_monitor
class TestEventDelivery:
    """
    Collect live events for EVENT_WAIT seconds and assert the expected signals
    from test-workloads.yaml appear.  These tests are intentionally slow —
    run them with -v to see progress.
    """

    @pytest_asyncio.fixture(scope="class")
    async def events(self):
        """Collect once for the whole class to avoid redundant wait periods."""
        print(f"\n  Collecting events for {EVENT_WAIT}s …")
        return await _collect_events(duration=EVENT_WAIT)

    async def test_received_at_least_one_event(self, events):
        assert len(events) > 0, "No events received — is the monitor running and port-forwarded?"

    async def test_crashloop_is_critical(self, events):
        """crashloop-test deployment must produce a CRITICAL event."""
        critical = _find(events, severity="CRITICAL")
        reasons  = {e["reason"] for e in critical}
        assert any(r.startswith("CrashLoop") or r == "BackOff" for r in reasons), (
            f"No CrashLoopBackOff CRITICAL event found. Reasons seen: {reasons}"
        )

    async def test_pending_produces_warning(self, events):
        """pending-test (impossible nodeSelector) must produce a WARNING."""
        warnings = _find(events, severity="WARNING")
        reasons  = {e["reason"] for e in warnings}
        assert "FailedScheduling" in reasons, (
            f"No FailedScheduling WARNING found. Reasons seen: {reasons}"
        )

    async def test_nginx_produces_info(self, events):
        """nginx-test healthy deployment must produce INFO events (Pulled, Started, etc.)."""
        infos   = _find(events, severity="INFO")
        reasons = {e["reason"] for e in infos}
        normal_reasons = {"Pulled", "Started", "Created", "Scheduled", "Pulling"}
        assert reasons & normal_reasons, (
            f"No INFO events from healthy workload. Reasons seen: {reasons}"
        )

    async def test_events_have_required_fields(self, events):
        """Every delivered event must carry the fields the dashboard and agent depend on."""
        required = {"event_id", "severity", "namespace", "resource_name",
                    "resource_kind", "reason", "message", "timestamp"}
        for ev in events:
            missing = required - ev.keys()
            assert not missing, f"Event {ev.get('event_id')} missing fields: {missing}"

    async def test_namespace_filter_works(self):
        """Subscribe to 'default' only — must not receive events from other namespaces."""
        events = await _collect_events(
            duration=30,
            subscription={
                "user_id":    "ns-filter-test",
                "severities": ["INFO", "WARNING", "CRITICAL"],
                "namespaces": ["default"],
                "role":       "viewer",
            },
        )
        for ev in events:
            assert ev["namespace"] == "default", (
                f"Received event from namespace '{ev['namespace']}' despite filter"
            )

    async def test_severity_filter_critical_only(self):
        """Subscribe CRITICAL only — must not receive INFO or WARNING events."""
        events = await _collect_events(
            duration=30,
            subscription={
                "user_id":    "sev-filter-test",
                "severities": ["CRITICAL"],
                "namespaces": [],
                "role":       "viewer",
            },
        )
        for ev in events:
            assert ev["severity"] == "CRITICAL", (
                f"Received {ev['severity']} event despite CRITICAL-only filter"
            )

    async def test_dedup_suppresses_repeats(self, events):
        """
        The same reason/resource/namespace triple should not appear more than
        once within the dedup window (60 s default).
        """
        seen: set[tuple] = set()
        duplicates = []
        for ev in events:
            key = (ev["namespace"], ev["resource_name"], ev["reason"])
            if key in seen:
                duplicates.append(key)
            seen.add(key)

        assert not duplicates, (
            f"Dedup failed — duplicate events delivered: {duplicates}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 – AgentNotifier (unit, no cluster needed)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAgentNotifier:
    """
    These tests mock the dispatcher so no cluster is needed.
    They verify the notifier attaches, filters by severity, and calls
    handle_agent_event with the right prompt.
    """

    def _make_event(self, severity="CRITICAL", reason="CrashLoopBackOff"):
        from monitoring.monitor import EnrichedEvent, Severity
        return EnrichedEvent(
            event_id      = "test-001",
            severity      = Severity[severity],
            namespace     = "default",
            resource_name = "crashloop-test-abc",
            resource_kind = "Pod",
            reason        = reason,
            message       = "container kept crashing",
            timestamp     = "2024-01-01T00:00:00+00:00",
            node          = "minikube",
            labels        = {"app": "crashloop-test"},
            annotations   = {},
            raw_count     = 5,
            first_seen    = "2024-01-01T00:00:00+00:00",
            last_seen     = "2024-01-01T00:01:00+00:00",
        )

    async def test_notifier_attaches_and_intercepts(self):
        from app.services.agent_notifier import AgentNotifier
        from monitoring.monitor import NotificationDispatcher, SubscriptionRegistry

        registry   = SubscriptionRegistry()
        dispatcher = NotificationDispatcher(registry)
        app_state  = MagicMock()

        notifier = AgentNotifier(dispatcher, app_state)

        called_with = []

        async def fake_notify(event):
            called_with.append(event)

        notifier._notify_agent = fake_notify
        notifier.attach()

        event = self._make_event("CRITICAL")
        await dispatcher.dispatch(event)

        await asyncio.sleep(0.1)   # let worker drain
        notifier.detach()

        assert len(called_with) == 1
        assert called_with[0].event_id == "test-001"

    async def test_info_events_not_forwarded_to_agent(self):
        from app.services.agent_notifier import AgentNotifier
        from monitoring.monitor import NotificationDispatcher, SubscriptionRegistry

        registry   = SubscriptionRegistry()
        dispatcher = NotificationDispatcher(registry)
        notifier   = AgentNotifier(dispatcher, MagicMock())

        called_with = []
        async def fake_notify(event):
            called_with.append(event)

        notifier._notify_agent = fake_notify
        notifier.attach()

        info_event = self._make_event("INFO", reason="Scheduled")
        await dispatcher.dispatch(info_event)

        await asyncio.sleep(0.1)
        notifier.detach()

        assert called_with == [], "INFO event should not reach agent"

    async def test_prompt_contains_key_fields(self):
        from app.services.agent_notifier import _build_prompt

        event  = self._make_event("CRITICAL")
        prompt = _build_prompt(event)

        assert "CRITICAL"            in prompt
        assert "default"             in prompt   # namespace
        assert "CrashLoopBackOff"    in prompt   # reason
        assert "container kept"      in prompt   # message fragment
        assert "Investigate"         in prompt   # agent instruction

    async def test_queue_full_drops_gracefully(self):
        """A full queue must log a warning and not raise."""
        from app.services.agent_notifier import AgentNotifier
        from monitoring.monitor import NotificationDispatcher, SubscriptionRegistry, EnrichedEvent, Severity

        registry   = SubscriptionRegistry()
        dispatcher = NotificationDispatcher(registry)
        notifier   = AgentNotifier(dispatcher, MagicMock())
        notifier._queue = asyncio.Queue(maxsize=1)   # tiny queue

        # Don't start worker — queue fills immediately
        async def slow_notify(event):
            await asyncio.sleep(999)

        notifier._notify_agent = slow_notify
        notifier.attach()

        # Flood it — should not raise
        for _ in range(5):
            await dispatcher.dispatch(self._make_event("CRITICAL"))

        notifier.detach()   # just verify no exception


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 – handle_agent_event DB persistence (unit, mocked DB)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestHandleAgentEvent:

    async def test_creates_alert_conversation_and_message(self):
        """
        First call with no existing conversation must create one and
        insert a ChatHistory row with sender='monitor'.
        """
        from app.api.routes.chat import handle_agent_event, AGENT_ALERT_CONVERSATION_TITLE
        from app.database.models import Conversation, ChatHistory

        # Build a minimal in-memory DB session mock
        mock_convo  = MagicMock(spec=Conversation)
        mock_convo.id = 42

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # no existing convo
        mock_db.flush = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.close = MagicMock()

        added_objects = []
        def capture_add(obj):
            added_objects.append(obj)
            if isinstance(obj, Conversation):
                obj.id = 42   # simulate flush assigning id

        mock_db.add = capture_add

        with patch("app.api.routes.chat.SessionLocal", return_value=mock_db):
            await handle_agent_event(
                prompt     = "[AUTO-ALERT] Severity: CRITICAL\nNamespace: default",
                event_dict = {"event_id": "test-001"},
                app_state  = MagicMock(),
            )

        conversations = [o for o in added_objects if isinstance(o, Conversation)]
        messages      = [o for o in added_objects if isinstance(o, ChatHistory)]

        assert len(conversations) == 1
        assert conversations[0].title == AGENT_ALERT_CONVERSATION_TITLE
        assert len(messages) == 1
        assert messages[0].sender == "monitor"
        assert "CRITICAL" in messages[0].message

    async def test_reuses_existing_conversation(self):
        """Second call must append to the existing conversation, not create a new one."""
        from app.api.routes.chat import handle_agent_event
        from app.database.models import Conversation, ChatHistory

        existing_convo    = MagicMock(spec=Conversation)
        existing_convo.id = 99

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_convo
        mock_db.close = MagicMock()

        added_objects = []
        mock_db.add = lambda o: added_objects.append(o)

        with patch("app.api.routes.chat.SessionLocal", return_value=mock_db):
            await handle_agent_event(
                prompt     = "[AUTO-ALERT] Severity: WARNING\nNamespace: default",
                event_dict = {},
                app_state  = MagicMock(),
            )

        conversations = [o for o in added_objects if isinstance(o, Conversation)]
        messages      = [o for o in added_objects if isinstance(o, ChatHistory)]

        assert len(conversations) == 0, "Must not create a new conversation"
        assert len(messages) == 1
        assert messages[0].conversation_id == 99
