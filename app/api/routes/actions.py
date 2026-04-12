"""Action request and approval endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.settings import get_settings
from app.schemas.api import ActionRequestCreate
from app.services.actions import ACTION_HANDLERS, execute_action_request
from app.state.store import (
    create_action_request,
    get_action_request,
    list_action_requests,
    mark_action_request_rejected,
)


router = APIRouter()


@router.post("/action-requests")
def create_action(payload: ActionRequestCreate) -> dict:
    """Create a pending action request."""
    return create_action_request(payload.model_dump())


@router.get("/action-requests")
def list_actions(status: Optional[str] = Query(default=None)) -> list[dict]:
    """List action requests, optionally filtered by status."""
    return list_action_requests(status=status)


@router.get("/action-requests/{action_id}")
def get_action(action_id: str) -> dict:
    """Fetch a single action request."""
    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    return record


@router.get("/action-types")
def get_action_types() -> dict:
    """List supported approval-gated action types."""
    return {"action_types": sorted(ACTION_HANDLERS)}


@router.post("/action-requests/{action_id}/approve")
def approve_action(action_id: str) -> dict:
    """Approve and execute an action request if mutations are enabled."""
    settings = get_settings()
    if settings.read_only_mode or not settings.mutations_enabled:
        raise HTTPException(
            status_code=409,
            detail="Mutations are disabled. Set AIOPS_READ_ONLY_MODE=false and AIOPS_ENABLE_MUTATIONS=true to execute actions.",
        )

    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="Action request is not pending")

    try:
        return execute_action_request(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/action-requests/{action_id}/reject")
def reject_action(action_id: str) -> dict:
    """Reject a pending action request."""
    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="Action request is not pending")

    record = mark_action_request_rejected(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    return record
