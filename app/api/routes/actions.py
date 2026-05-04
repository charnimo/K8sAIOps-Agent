"""Action request and approval endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user, get_permission_label, require_permission, user_has_permission
from app.core.settings import get_settings
from app.database.models import User
from app.schemas.api import ActionRequestCreate
from app.services.actions import ACTION_HANDLERS, execute_action_request
from app.state.store import (
    create_action_request,
    get_action_request,
    list_action_requests,
    mark_action_request_rejected,
)


router = APIRouter()

ACTION_PERMISSION_MAP = {
    "delete_pod": "pods:delete",
    "exec_pod": "pods:exec",
    "scale_deployment": "deployments:scale",
    "restart_deployment": "deployments:restart",
    "rollback_deployment": "deployments:rollback",
    "patch_resource_limits": "deployments:patch",
    "patch_env_var": "deployments:patch",
    "scale_statefulset": "workloads:statefulsets:scale",
    "restart_statefulset": "workloads:statefulsets:restart",
    "restart_daemonset": "workloads:daemonsets:restart",
    "update_daemonset_image": "workloads:daemonsets:update_image",
    "delete_job": "workloads:jobs:delete",
    "suspend_job": "workloads:jobs:suspend",
    "resume_job": "workloads:jobs:resume",
    "suspend_cronjob": "workloads:cronjobs:suspend",
    "resume_cronjob": "workloads:cronjobs:resume",
    "create_service": "services:create",
    "patch_service": "services:patch",
    "delete_service": "services:delete",
    "create_configmap": "configmaps:create",
    "patch_configmap": "configmaps:patch",
    "delete_configmap": "configmaps:delete",
    "create_secret": "secrets:create",
    "update_secret": "secrets:update",
    "delete_secret": "secrets:delete",
    "cordon_node": "cluster:nodes:cordon",
    "uncordon_node": "cluster:nodes:uncordon",
    "drain_node": "cluster:nodes:drain",
    "create_pvc": "storage:pvcs:create",
    "patch_pvc": "storage:pvcs:patch",
    "delete_pvc": "storage:pvcs:delete",
    "create_ingress": "ingresses:create",
    "patch_ingress": "ingresses:patch",
    "delete_ingress": "ingresses:delete",
    "create_hpa": "hpa:create",
    "patch_hpa": "hpa:patch",
    "delete_hpa": "hpa:delete",
    "create_namespace": "cluster:namespaces:create",
    "delete_namespace": "cluster:namespaces:delete",
}


def _authorize_action_permission(action_type: str, target: dict, user: User) -> None:
    permission_key = ACTION_PERMISSION_MAP.get(action_type)
    if permission_key is None:
        raise HTTPException(status_code=400, detail=f"Unsupported action type: {action_type}")

    namespace = target.get("namespace", "default") if isinstance(target, dict) else "default"
    if not user_has_permission(user, permission_key, namespace=namespace):
        permission_label = get_permission_label(permission_key)
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission_label}")


@router.post("/action-requests")
def create_action(
    payload: ActionRequestCreate,
    user: User = Depends(get_current_user),
) -> dict:
    """Create a pending action request."""
    _authorize_action_permission(payload.type, payload.target.model_dump(), user)
    return create_action_request(payload.model_dump())


@router.get("/action-requests")
def list_actions(
    status: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List action requests, optionally filtered by status."""
    return list_action_requests(status=status)


@router.get("/action-requests/{action_id}")
def get_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Fetch a single action request."""
    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    return record


@router.get("/action-types")
def get_action_types(user: User = Depends(get_current_user)) -> dict:
    """List supported approval-gated action types."""
    return {"action_types": sorted(ACTION_HANDLERS)}


@router.post("/action-requests/{action_id}/approve")
def approve_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Approve and execute an action request if mutations are enabled."""
    record = get_action_request(action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action request not found")
    if record["status"] != "pending":
        raise HTTPException(status_code=409, detail="Action request is not pending")

    _authorize_action_permission(record["type"], record["target"], user)

    settings = get_settings()
    if settings.read_only_mode or not settings.mutations_enabled:
        raise HTTPException(
            status_code=409,
            detail="Mutations are disabled. Set AIOPS_READ_ONLY_MODE=false and AIOPS_ENABLE_MUTATIONS=true to execute actions.",
        )

    try:
        return execute_action_request(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/action-requests/{action_id}/reject")
def reject_action(
    action_id: str,
    user: User = Depends(get_current_user),
) -> dict:
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
