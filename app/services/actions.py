"""Controlled execution of approved action requests."""

from typing import Any, Callable, Optional

from Tools import (
    audit,
    configmaps,
    daemonsets,
    deployments,
    hpa,
    ingress,
    jobs,
    nodes,
    pods,
    secrets,
    services,
    statefulsets,
    storage,
)
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


def _bool_param(params: dict[str, Any], key: str, default: bool) -> bool:
    """Normalize a bool-like request parameter."""
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _keys_for_audit(data: Any) -> list[str]:
    """Extract dict keys safely for audit payloads."""
    if isinstance(data, dict):
        return list(data.keys())
    return []


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


def _handle_create_service(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = services.create_service(
        name=name,
        namespace=namespace,
        service_type=str(params.get("service_type", "ClusterIP")),
        selector=params.get("selector"),
        ports=params.get("ports"),
        labels=params.get("labels"),
    )
    audit.audit_service_action("create", name, namespace, result.get("success", False), _audit_error(result))
    return result


def _handle_patch_service(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = services.patch_service(
        name=name,
        namespace=namespace,
        selector=params.get("selector"),
        labels=params.get("labels"),
        ports=params.get("ports"),
    )
    audit.audit_service_action("patch", name, namespace, result.get("success", False), _audit_error(result))
    return result


def _handle_delete_service(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = services.delete_service(name=name, namespace=namespace)
    audit.audit_service_action("delete", name, namespace, result.get("success", False), _audit_error(result))
    return result


def _handle_create_configmap(record: dict, params: dict, name: str, namespace: str) -> dict:
    data = _require_param(params, "data")
    result = configmaps.create_configmap(
        name=name,
        namespace=namespace,
        data=data,
        labels=params.get("labels"),
    )
    audit.audit_configmap_action(
        "create",
        name,
        namespace,
        result.get("success", False),
        keys=_keys_for_audit(data),
        error=_audit_error(result),
    )
    return result


def _handle_patch_configmap(record: dict, params: dict, name: str, namespace: str) -> dict:
    data = _require_param(params, "data")
    result = configmaps.patch_configmap(name=name, namespace=namespace, data=data)
    audit.audit_configmap_action(
        "patch",
        name,
        namespace,
        result.get("success", False),
        keys=_keys_for_audit(data),
        error=_audit_error(result),
    )
    return result


def _handle_delete_configmap(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = configmaps.delete_configmap(name=name, namespace=namespace)
    audit.audit_configmap_action("delete", name, namespace, result.get("success", False), error=_audit_error(result))
    return result


def _handle_create_secret(record: dict, params: dict, name: str, namespace: str) -> dict:
    data = _require_param(params, "data")
    result = secrets.create_secret(
        name=name,
        namespace=namespace,
        data=data,
        secret_type=str(params.get("secret_type", "Opaque")),
    )
    audit.audit_secret_action(
        "create",
        name,
        namespace,
        result.get("success", False),
        keys=_keys_for_audit(data),
        error=_audit_error(result),
    )
    return result


def _handle_update_secret(record: dict, params: dict, name: str, namespace: str) -> dict:
    data = _require_param(params, "data")
    result = secrets.update_secret(name=name, namespace=namespace, data=data)
    audit.audit_secret_action(
        "update",
        name,
        namespace,
        result.get("success", False),
        keys=_keys_for_audit(data),
        error=_audit_error(result),
    )
    return result


def _handle_delete_secret(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = secrets.delete_secret(name=name, namespace=namespace)
    audit.audit_secret_action("delete", name, namespace, result.get("success", False), error=_audit_error(result))
    return result


def _handle_cordon_node(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = nodes.cordon_node(name=name)
    audit.audit_node_action("cordon", name, result.get("success", False), _audit_error(result))
    return result


def _handle_uncordon_node(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = nodes.uncordon_node(name=name)
    audit.audit_node_action("uncordon", name, result.get("success", False), _audit_error(result))
    return result


def _handle_drain_node(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = nodes.drain_node(
        name=name,
        ignore_daemonsets=_bool_param(params, "ignore_daemonsets", True),
        grace_period_seconds=int(params.get("grace_period_seconds", 30)),
    )
    audit.audit_node_action("drain", name, result.get("success", False), _audit_error(result))
    return result


def _handle_create_pvc(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = storage.create_pvc(
        name=name,
        namespace=namespace,
        size=str(params.get("size", "1Gi")),
        access_modes=params.get("access_modes"),
        storage_class=params.get("storage_class"),
        labels=params.get("labels"),
    )
    audit.log_action(
        "pvc_create",
        name,
        namespace,
        result.get("success", False),
        details=params,
        error_message=_audit_error(result),
    )
    return result


def _handle_patch_pvc(record: dict, params: dict, name: str, namespace: str) -> dict:
    labels = _require_param(params, "labels")
    result = storage.patch_pvc(name=name, namespace=namespace, labels=labels)
    audit.log_action(
        "pvc_patch",
        name,
        namespace,
        result.get("success", False),
        details={"labels": labels},
        error_message=_audit_error(result),
    )
    return result


def _handle_delete_pvc(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = storage.delete_pvc(name=name, namespace=namespace)
    audit.log_action("pvc_delete", name, namespace, result.get("success", False), error_message=_audit_error(result))
    return result


def _handle_create_ingress(record: dict, params: dict, name: str, namespace: str) -> dict:
    rules = _require_param(params, "rules")
    result = ingress.create_ingress(
        name=name,
        namespace=namespace,
        rules=rules,
        tls=params.get("tls"),
        annotations=params.get("annotations"),
        labels=params.get("labels"),
    )
    audit.log_action(
        "ingress_create",
        name,
        namespace,
        result.get("success", False),
        details={"rules": rules},
        error_message=_audit_error(result),
    )
    return result


def _handle_patch_ingress(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = ingress.patch_ingress(
        name=name,
        namespace=namespace,
        labels=params.get("labels"),
        annotations=params.get("annotations"),
    )
    audit.log_action(
        "ingress_patch",
        name,
        namespace,
        result.get("success", False),
        details={"labels": params.get("labels"), "annotations": params.get("annotations")},
        error_message=_audit_error(result),
    )
    return result


def _handle_delete_ingress(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = ingress.delete_ingress(name=name, namespace=namespace)
    audit.log_action("ingress_delete", name, namespace, result.get("success", False), error_message=_audit_error(result))
    return result


def _handle_create_hpa(record: dict, params: dict, name: str, namespace: str) -> dict:
    target_name = str(_require_param(params, "target_name"))
    result = hpa.create_hpa(
        name=name,
        namespace=namespace,
        target_kind=str(params.get("target_kind", "Deployment")),
        target_name=target_name,
        min_replicas=int(params.get("min_replicas", 1)),
        max_replicas=int(params.get("max_replicas", 10)),
        target_cpu_percent=params.get("target_cpu_percent"),
        target_memory_percent=params.get("target_memory_percent"),
        labels=params.get("labels"),
    )
    audit.log_action(
        "hpa_create",
        name,
        namespace,
        result.get("success", False),
        details={"target_name": target_name},
        error_message=_audit_error(result),
    )
    return result


def _handle_patch_hpa(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = hpa.patch_hpa(
        name=name,
        namespace=namespace,
        min_replicas=params.get("min_replicas"),
        max_replicas=params.get("max_replicas"),
        labels=params.get("labels"),
    )
    audit.log_action(
        "hpa_patch",
        name,
        namespace,
        result.get("success", False),
        details={"min_replicas": params.get("min_replicas"), "max_replicas": params.get("max_replicas")},
        error_message=_audit_error(result),
    )
    return result


def _handle_delete_hpa(record: dict, params: dict, name: str, namespace: str) -> dict:
    result = hpa.delete_hpa(name=name, namespace=namespace)
    audit.log_action("hpa_delete", name, namespace, result.get("success", False), error_message=_audit_error(result))
    return result


def _handle_exec_pod(record: dict, params: dict, name: str, namespace: str) -> dict:
    command = _require_param(params, "command")
    result = pods.exec_pod(
        name=name,
        namespace=namespace,
        command=command,
        stdin=_bool_param(params, "stdin", False),
        stdout=_bool_param(params, "stdout", True),
        stderr=_bool_param(params, "stderr", True),
        tty=_bool_param(params, "tty", False),
    )
    audit.log_action(
        "pod_exec",
        name,
        namespace,
        result.get("success", False),
        details={"command": command},
        error_message=_audit_error(result),
    )
    return result


ACTION_HANDLERS: dict[str, ActionHandler] = {
    "delete_pod": _handle_delete_pod,
    "exec_pod": _handle_exec_pod,
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
    "create_service": _handle_create_service,
    "patch_service": _handle_patch_service,
    "delete_service": _handle_delete_service,
    "create_configmap": _handle_create_configmap,
    "patch_configmap": _handle_patch_configmap,
    "delete_configmap": _handle_delete_configmap,
    "create_secret": _handle_create_secret,
    "update_secret": _handle_update_secret,
    "delete_secret": _handle_delete_secret,
    "cordon_node": _handle_cordon_node,
    "uncordon_node": _handle_uncordon_node,
    "drain_node": _handle_drain_node,
    "create_pvc": _handle_create_pvc,
    "patch_pvc": _handle_patch_pvc,
    "delete_pvc": _handle_delete_pvc,
    "create_ingress": _handle_create_ingress,
    "patch_ingress": _handle_patch_ingress,
    "delete_ingress": _handle_delete_ingress,
    "create_hpa": _handle_create_hpa,
    "patch_hpa": _handle_patch_hpa,
    "delete_hpa": _handle_delete_hpa,
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
