"""
Thin glue: starts monitor components inside the FastAPI lifespan
and exposes REST + WebSocket endpoints for the dashboard.
"""
from contextlib import asynccontextmanager
import asyncio
import contextlib
import json
import logging
from fastapi import FastAPI, WebSocket

from monitoring.monitor import build_monitor_components, get_router, Subscription
from app.services.agent_notifier import AgentNotifier

logger = logging.getLogger(__name__)


# Lifespan
@asynccontextmanager
async def monitor_lifespan(app: FastAPI):
    logger.info("[MONITOR] Building monitor components")
    components = await build_monitor_components()
    app.state.monitor = components
    logger.info("[MONITOR] Monitor components built and stored in app.state")

    logger.info("[MONITOR] Initializing AgentNotifier")
    notifier = AgentNotifier(components["dispatcher"], app.state)
    notifier.attach()
    app.state.agent_notifier = notifier

    logger.info("[MONITOR] Starting watcher task")
    task = asyncio.create_task(components["watcher"].start())

    try:
        yield
    finally:
        notifier.detach()
        task.cancel()
        with contextlib.suppress(Exception):
            await task


# Registration
def register_monitor(app: FastAPI):
    """Call once in main.py after creating FastAPI app."""
    logger.info("[MONITOR] Registering monitor endpoints")

    # REST routes (/monitor/*)
    app.include_router(get_router())
    logger.info("[MONITOR] REST routes registered")

    # WebSocket bridge to monitor dispatcher
    @app.websocket("/ws/events")
    async def events_ws(ws: WebSocket):
        """
        FastAPI WebSocket endpoint that bridges to the monitor dispatcher.
        Handles subscription and event routing just like the standalone server would.
        """
        logger.info("[MONITOR] WebSocket /ws/events connection attempt from %s", ws.client)
        await ws.accept()
        logger.info("[MONITOR] WebSocket connection accepted")

        if not hasattr(app.state, 'monitor'):
            logger.error("[MONITOR] app.state.monitor not available!")
            await ws.close(code=1011, reason="Monitor not initialized")
            return

        components = app.state.monitor
        registry = components["registry"]
        dispatcher = components["dispatcher"]
        ns_cache = components["ns_cache"]

        try:
            # Receive subscription data with timeout
            import json
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
            sub_data = json.loads(raw)
            logger.info("[MONITOR/WS] Subscription data received: user_id=%s", sub_data.get("user_id"))

            # Create and register subscription
            from monitoring.monitor import Subscription
            sub = Subscription(
                user_id=sub_data.get("user_id", "anonymous"),
                namespaces=set(sub_data.get("namespaces", [])),
                teams=set(sub_data.get("teams", [])),
                severities=set(sub_data.get("severities", ["INFO", "WARNING", "CRITICAL"])),
                role=sub_data.get("role", "viewer"),
            )
            registry.register(ws, sub)
            logger.info("[MONITOR/WS] User %s subscribed", sub.user_id)

            # Send subscription confirmation with history
            response = {
                "type": "SUBSCRIBED",
                "user_id": sub.user_id,
                "message": "Subscription active",
                "history": dispatcher.recent_events(20),
                "namespaces": ns_cache.known_namespaces(),
            }
            await ws.send_json(response)
            logger.info("[MONITOR/WS] Subscription confirmation sent with %d history events", len(response["history"]))

            # Listen for client messages (PING, UPDATE_SUBSCRIPTION, etc.)
            while True:
                try:
                    message = await ws.receive_text()
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    logger.debug("[MONITOR/WS] Message from %s: type=%s", sub.user_id, msg_type)

                    if msg_type == "PING":
                        await ws.send_json({"type": "PONG", "ts": asyncio.get_event_loop().time()})

                    elif msg_type == "UPDATE_SUBSCRIPTION":
                        sub.namespaces = set(data.get("namespaces", []))
                        sub.teams = set(data.get("teams", []))
                        sub.severities = set(data.get("severities", ["INFO", "WARNING", "CRITICAL"]))
                        await ws.send_json({"type": "SUBSCRIPTION_UPDATED"})
                        logger.info("[MONITOR/WS] Subscription updated for %s", sub.user_id)

                    elif msg_type == "GET_HISTORY":
                        limit = int(data.get("limit", 50))
                        await ws.send_json({
                            "type": "HISTORY",
                            "events": dispatcher.recent_events(limit),
                        })

                    elif msg_type == "GET_NAMESPACES":
                        await ws.send_json({
                            "type": "NAMESPACES",
                            "namespaces": ns_cache.known_namespaces(),
                        })

                except json.JSONDecodeError:
                    logger.warning("[MONITOR/WS] JSON decode error from %s", sub.user_id)
                except asyncio.CancelledError:
                    logger.info("[MONITOR/WS] Cancelled for %s", sub.user_id)
                    raise

        except asyncio.TimeoutError:
            logger.warning("[MONITOR] WebSocket handshake timeout from %s", ws.client)
            await ws.close(code=1002, reason="Handshake timeout")
        except Exception as exc:
            logger.error("[MONITOR] WebSocket error: %s", exc)
            try:
                await ws.close(code=1011, reason="Internal server error")
            except Exception:
                pass
        finally:
            try:
                registry.unregister(ws)
                logger.info("[MONITOR] WebSocket connection closed from %s", ws.client)
            except Exception:
                pass