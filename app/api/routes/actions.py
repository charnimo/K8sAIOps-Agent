"""Action request and approval endpoints."""

from fastapi import APIRouter, HTTPException

from app.core.settings import get_settings
from app.schemas.api import ActionRequestCreate
from app.services.actions import execute_action_request
from app.state.store import (
    create_action_request,
    get_action_request,
    mark_action_request_rejected,
)


router = APIRouter()


@router.post("/action-requests")
def create_action(payload: ActionRequestCreate) -> dict:
    """Create a pending action request."""
    return create_action_request(payload.model_dump())


@router.get("/action-requests/{action_id}")
def get_action(action_id: str) -> dict:
    """Fetch a single action request."""
    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    return record


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
    record = mark_action_request_rejected(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    return record

