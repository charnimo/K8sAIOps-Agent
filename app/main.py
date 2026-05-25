"""Application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.settings import get_settings

# Database imports
from app.database.database import Base, engine, seed_mock_chat_history, seed_permission_catalog

# Monitor imports
try:
    from monitoring.monitor import build_monitor_components, get_router as get_monitor_router
    from app.services.monitor_service import register_monitor
    MONITOR_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    logging.warning("Monitor not available: %s", e)
    MONITOR_AVAILABLE = False

# Initialize the SQLite tables
Base.metadata.create_all(bind=engine)
seed_permission_catalog()
seed_mock_chat_history()

settings = get_settings()


# ─── Lifespan management ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application resources."""
    tasks = []
    try:
        if MONITOR_AVAILABLE:
            # Build monitor components
            components = await build_monitor_components()
            app.state.monitor = components

            # Attach AgentNotifier so the agent receives notifications
            from app.services.agent_notifier import AgentNotifier
            notifier = AgentNotifier(components["dispatcher"], app.state)
            notifier.attach()
            app.state.agent_notifier = notifier

            # Start watcher and WebSocket server
            watcher_task = asyncio.create_task(components["watcher"].start())
            ws_task = asyncio.create_task(components["ws_server"].start())
            tasks.extend([watcher_task, ws_task])

        yield
    finally:
            if MONITOR_AVAILABLE:
                try:
                    notifier.detach()
                except Exception:
                    pass
            for task in tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API gateway for the Kubernetes AIOps proof of concept.",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files to serve the UI
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", summary="Serve Dashboard UI", tags=["UI"])
def read_root():
    return FileResponse("app/static/index.html")

app.include_router(api_router)

# Include monitor router and WebSocket endpoint if available
if MONITOR_AVAILABLE:
    app.include_router(get_monitor_router())
    register_monitor(app)

