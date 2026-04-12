"""Main API router."""

from fastapi import APIRouter

from app.api.routes import actions, audit, chat, dashboard, diagnostics, events, health, resources


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(resources.router, prefix="/resources", tags=["resources"])
api_router.include_router(diagnostics.router, prefix="/diagnostics", tags=["diagnostics"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(actions.router, tags=["actions"])
api_router.include_router(audit.router, tags=["audit"])

