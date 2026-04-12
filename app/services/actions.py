"""Controlled execution of approved action requests."""

from typing import Any, Callable, Optional

from Tools import audit, daemonsets, deployments, jobs, pods, statefulsets
from app.state.store import get_action_request, mark_action_request_executed


ActionHandler = Callable[[dict, dict, str, str], dict]


def _audit_error(result: dict) -> Optional[str]:
    """Return an error message only when the action failed."""
    if result.get("success", False):
        return None
    return result.get("message")


def _require_param(params: dict[str, Any], key: str) -> Any:
    """Read a required action parameter or raise a validation error."""
    if key not in params:
        raise ValueError(f"{key} is required in params")
    return params[key]


def _handle_delete_pod(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = pods.delete_pod(name=name, namespace=namespace)
    audit.audit_pod_delete(name, namespace, result.get("success", False), _audit_error(result))
    return result


def _handle_scale_deployment(record: dict, params: dict, name: str, namespace: str) -> dict:
    replicas = int(_require_param(params, "replicas"))
    result = deployments.scale_deployment(name=name, namespace=namespace, replicas=replicas)
    audit.audit_deployment_scale(name, namespace, replicas, result.get("success", False), _audit_error(result))
    return result


def _handle_restart_deployment(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = deployments.rollout_restart(name=name, namespace=namespace)
    audit.audit_rollout_restart(name, namespace, "deployment", result.get("success", False), _audit_error(result))
    return result


def _handle_rollback_deployment(record: dict, params: dict, name: str, namespace: str) -> dict:
    revision = params.get("revision")
    result = deployments.rollback_deployment(name=name, namespace=namespace, revision=revision)
    audit.log_action(
        "deployment_rollback",
        name,
        namespace,
        result.get("success", False),
        details={"revision": revision},
        error_message=_audit_error(result),
    )
    return result


def _handle_patch_resource_limits(record: dict, params: dict, name: str, namespace: str) -> dict:
    container_name = params.get("container_name")
    changes = {
        "cpu_request": params.get("cpu_request"),
        "cpu_limit": params.get("cpu_limit"),
        "memory_request": params.get("memory_request"),
        "memory_limit": params.get("memory_limit"),
    }
    if not any(value is not None for value in changes.values()):
        raise ValueError("At least one resource limit or request field must be provided")

    result = deployments.patch_resource_limits(
        name=name,
        namespace=namespace,
        container_name=container_name,
        cpu_request=changes["cpu_request"],
        cpu_limit=changes["cpu_limit"],
        memory_request=changes["memory_request"],
        memory_limit=changes["memory_limit"],
    )
    audit.audit_patch_resource_limits(
        name,
        namespace,
        container_name or "auto",
        changes,
        result.get("success", False),
        _audit_error(result),
    )
    return result


def _handle_patch_env_var(record: dict, params: dict, name: str, namespace: str) -> dict:
    key = str(_require_param(params, "key"))
    value = str(_require_param(params, "value"))
    container_name = params.get("container_name")
    result = deployments.patch_env_var(
        name=name,
        namespace=namespace,
        container_name=container_name,
        key=key,
        value=value,
    )
    audit.audit_patch_env_var(
        name,
        namespace,
        container_name or "auto",
        key,
        result.get("success", False),
        _audit_error(result),
    )
    return result


def _handle_scale_statefulset(record: dict, params: dict, name: str, namespace: str) -> dict:
    replicas = int(_require_param(params, "replicas"))
    result = statefulsets.scale_statefulset(name=name, namespace=namespace, replicas=replicas)
    audit.audit_statefulset_scale(name, namespace, replicas, result.get("success", False), _audit_error(result))
    return result


def _handle_restart_statefulset(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = statefulsets.restart_statefulset(name=name, namespace=namespace)
    audit.audit_rollout_restart(name, namespace, "statefulset", result.get("success", False), _audit_error(result))
    return result


def _handle_restart_daemonset(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = daemonsets.restart_daemonset(name=name, namespace=namespace)
    audit.audit_rollout_restart(name, namespace, "daemonset", result.get("success", False), _audit_error(result))
    return result


def _handle_update_daemonset_image(record: dict, params: dict, name: str, namespace: str) -> dict:
    container = str(_require_param(params, "container"))
    image = str(_require_param(params, "image"))
    result = daemonsets.update_daemonset_image(
        name=name,
        namespace=namespace,
        container=container,
        image=image,
    )
    audit.audit_daemonset_image_update(
        name,
        namespace,
        container,
        image,
        result.get("success", False),
        _audit_error(result),
    )
    return result


def _handle_delete_job(record: dict, params: dict, name: str, namespace: str) -> dict:
    propagation_policy = str(params.get("propagation_policy", "Foreground"))
    result = jobs.delete_job(name=name, namespace=namespace, propagation_policy=propagation_policy)
    audit.log_action(
        "job_delete",
        name,
        namespace,
        result.get("success", False),
        details={"propagation_policy": propagation_policy},
        error_message=_audit_error(result),
    )
    return result


def _handle_suspend_job(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = jobs.suspend_job(name=name, namespace=namespace)
    audit.log_action("job_suspend", name, namespace, result.get("success", False), error_message=_audit_error(result))
    return result


def _handle_suspend_cronjob(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = jobs.suspend_cronjob(name=name, namespace=namespace)
    audit.log_action(
        "cronjob_suspend",
        name,
        namespace,
        result.get("success", False),
        error_message=_audit_error(result),
    )
    return result


def _handle_resume_cronjob(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = jobs.resume_cronjob(name=name, namespace=namespace)
    audit.log_action(
        "cronjob_resume",
        name,
        namespace,
        result.get("success", False),
        error_message=_audit_error(result),
    )
    return result


ACTION_HANDLERS: dict[str, ActionHandler] = {
    "delete_pod": _handle_delete_pod,
    "scale_deployment": _handle_scale_deployment,
    "restart_deployment": _handle_restart_deployment,
    "rollback_deployment": _handle_rollback_deployment,
    "patch_resource_limits": _handle_patch_resource_limits,
    "patch_env_var": _handle_patch_env_var,
    "scale_statefulset": _handle_scale_statefulset,
    "restart_statefulset": _handle_restart_statefulset,
    "restart_daemonset": _handle_restart_daemonset,
    "update_daemonset_image": _handle_update_daemonset_image,
    "delete_job": _handle_delete_job,
    "suspend_job": _handle_suspend_job,
    "suspend_cronjob": _handle_suspend_cronjob,
    "resume_cronjob": _handle_resume_cronjob,
}


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

    handler = ACTION_HANDLERS.get(action_type)
    if handler is None:
        raise ValueError(f"Unsupported action type: {action_type}")

    result = handler(record, params, name, namespace)
    return mark_action_request_executed(action_id, result)
