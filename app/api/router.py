"""Main API router."""

from fastapi import APIRouter

from app.api.routes import (
    actions,
    audit,
    auth,
    chat,
    cluster,
    configuration,
    dashboard,
    diagnostics,
    events,
    governance,
    health,
    observability,
    resources,
    workloads,
)


api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(workloads.router, prefix="/workloads", tags=["workloads"])
api_router.include_router(cluster.router, prefix="/cluster", tags=["cluster"])
api_router.include_router(configuration.router, prefix="/config", tags=["configuration"])
api_router.include_router(governance.router, prefix="/governance", tags=["governance"])
api_router.include_router(observability.router, prefix="/observability", tags=["observability"])
api_router.include_router(diagnostics.router, prefix="/diagnostics", tags=["diagnostics"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(actions.router, tags=["actions"])
api_router.include_router(audit.router, tags=["audit"])
