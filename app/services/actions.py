"""Controlled execution of approved action requests."""

from typing import Optional

from Tools import audit, deployments, pods
from app.state.store import get_action_request, mark_action_request_executed


def _audit_error(result: dict) -> Optional[str]:
    """Return an error message only when the action failed."""
    if result.get("success", False):
        return None
    return result.get("message")


def execute_action_request(action_id: str) -> dict:
    """Execute a supported pending action request and persist the outcome."""
    record = get_action_request(action_id)
    if record is None:
        raise ValueError("Action request not found")

    action_type = record["type"]
    target = record["target"]
    params = record.get("params", {})
    name = target["name"]
    namespace = target.get("namespace", "default")

    if action_type == "delete_pod":
        result = pods.delete_pod(name=name, namespace=namespace)
        audit.audit_pod_delete(name, namespace, result.get("success", False), _audit_error(result))
    elif action_type == "scale_deployment":
        if "replicas" not in params:
            raise ValueError("scale_deployment requires params.replicas")
        replicas = int(params["replicas"])
        result = deployments.scale_deployment(name=name, namespace=namespace, replicas=replicas)
        audit.audit_deployment_scale(name, namespace, replicas, result.get("success", False), _audit_error(result))
    elif action_type == "restart_deployment":
        result = deployments.rollout_restart(name=name, namespace=namespace)
        audit.audit_rollout_restart(name, namespace, "deployment", result.get("success", False), _audit_error(result))
    else:
        raise ValueError(f"Unsupported action type: {action_type}")

    return mark_action_request_executed(action_id, result)
