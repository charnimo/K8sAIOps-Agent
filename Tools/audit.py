"""
tools/audit.py

Action audit logging — track what the agent does.

All agent actions (delete pod, scale deployment, patch config, etc.) must be logged
for audit, compliance, and debugging purposes.

Functions:
  - log_action(action_type, resource, namespace, success, details, user_id)
  - get_action_history(limit, filter_by)
  - clear_old_logs(days)
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Audit log file location (can be overridden via env var)
import os
AUDIT_LOG_FILE = os.getenv("K8S_AUDIT_LOG_FILE", "/tmp/k8s-agent-audit.jsonl")


def log_action(
    action_type: str,
    resource: str,
    namespace: str = "default",
    success: bool = True,
    details: Optional[dict] = None,
    user_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    """
    Log an agent action for audit purposes.

    Args:
        action_type:    Type of action ("delete_pod", "scale_deployment", "patch_config", etc.)
        resource:       Resource name (pod name, deployment name, etc.)
        namespace:      Kubernetes namespace
        success:        Whether the action succeeded
        details:        Additional context (parameters passed, result, etc.)
        user_id:        Who triggered this (agent, admin, etc.)
        error_message:  If failed, the error message

    Returns:
        The audit log entry as a dict
    """
    entry = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "action_type":    action_type,
        "resource":       resource,
        "namespace":      namespace,
        "success":        success,
        "user_id":        user_id or "ai-agent",
        "details":        details or {},
        "error_message":  error_message,
    }

    # Write to file
    try:
        Path(AUDIT_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.info(f"✓ Audit logged: {action_type} {namespace}/{resource} → {success}")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

    return entry


def get_action_history(
    limit: int = 100,
    filter_by: Optional[dict] = None,
) -> list[dict]:
    """
    Retrieve recent audit log entries.

    Args:
        limit:      Max entries to return
        filter_by:  Dict with keys like {"action_type": "delete_pod", "success": True}

    Returns:
        List of audit entries (newest first)
    """
    if not Path(AUDIT_LOG_FILE).exists():
        return []

    entries = []
    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    
                    # Apply filters
                    if filter_by:
                        if not all(entry.get(k) == v for k, v in filter_by.items()):
                            continue
                    
                    entries.append(entry)
    except Exception as e:
        logger.error(f"Error reading audit log: {e}")

    # Return newest first, limited
    return entries[-limit:][::-1]


def clear_old_logs(days: int = 30) -> int:
    """
    Delete audit log entries older than N days.

    Args:
        days: Entries older than this many days are deleted

    Returns:
        Number of entries deleted
    """
    if not Path(AUDIT_LOG_FILE).exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept_entries = []
    deleted = 0

    try:
        with open(AUDIT_LOG_FILE, "r") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time > cutoff:
                        kept_entries.append(entry)
                    else:
                        deleted += 1

        # Rewrite file with kept entries
        with open(AUDIT_LOG_FILE, "w") as f:
            for entry in kept_entries:
                f.write(json.dumps(entry) + "\n")

        logger.info(f"✓ Audit log cleanup: deleted {deleted} entries older than {days} days")
    except Exception as e:
        logger.error(f"Error during audit log cleanup: {e}")

    return deleted


# ─────────────────────────────────────────────
# CONVENIENCE WRAPPERS (call these from tools)
# ─────────────────────────────────────────────

def audit_pod_delete(pod_name: str, namespace: str, success: bool, error: Optional[str] = None):
    """Log a pod deletion."""
    return log_action(
        "pod_delete",
        pod_name,
        namespace,
        success,
        error_message=error,
    )


def audit_deployment_scale(
    deployment_name: str,
    namespace: str,
    target_replicas: int,
    success: bool,
    error: Optional[str] = None,
):
    """Log a deployment scaling operation."""
    return log_action(
        "deployment_scale",
        deployment_name,
        namespace,
        success,
        details={"target_replicas": target_replicas},
        error_message=error,
    )


def audit_config_patch(
    config_name: str,
    namespace: str,
    config_type: str,  # "configmap" or "secret"
    success: bool,
    error: Optional[str] = None,
):
    """Log a ConfigMap or Secret patch."""
    return log_action(
        f"{config_type}_patch",
        config_name,
        namespace,
        success,
        error_message=error,
    )


def audit_node_action(
    action: str,  # "cordon", "uncordon", "drain"
    node_name: str,
    success: bool,
    error: Optional[str] = None,
):
    """Log a node-level action."""
    return log_action(
        f"node_{action}",
        node_name,
        "cluster-wide",
        success,
        error_message=error,
    )


# ─────────────────────────────────────────────
# EXTENDED CONVENIENCE WRAPPERS
# ─────────────────────────────────────────────

def audit_rollout_restart(resource_name: str, namespace: str, kind: str, success: bool, error: Optional[str] = None):
    """Log a rollout restart (Deployment, StatefulSet, DaemonSet)."""
    return log_action(f"{kind.lower()}_restart", resource_name, namespace, success, error_message=error)


def audit_statefulset_scale(name: str, namespace: str, target_replicas: int, success: bool, error: Optional[str] = None):
    return log_action("statefulset_scale", name, namespace, success,
                      details={"target_replicas": target_replicas}, error_message=error)


def audit_daemonset_image_update(name: str, namespace: str, container: str, image: str, success: bool, error: Optional[str] = None):
    return log_action("daemonset_image_update", name, namespace, success,
                      details={"container": container, "image": image}, error_message=error)


def audit_job_action(action: str, name: str, namespace: str, success: bool, error: Optional[str] = None):
    """Log a job/cronjob action: delete, suspend, resume."""
    return log_action(f"job_{action}", name, namespace, success, error_message=error)


def audit_configmap_action(action: str, name: str, namespace: str, success: bool, keys: Optional[list] = None, error: Optional[str] = None):
    """Log a ConfigMap action: create, patch, delete."""
    return log_action(f"configmap_{action}", name, namespace, success,
                      details={"keys": keys or []}, error_message=error)


def audit_secret_action(action: str, name: str, namespace: str, success: bool, keys: Optional[list] = None, error: Optional[str] = None):
    """Log a Secret action: create, update, delete."""
    return log_action(f"secret_{action}", name, namespace, success,
                      details={"keys": keys or []}, error_message=error)


def audit_service_action(action: str, name: str, namespace: str, success: bool, error: Optional[str] = None):
    """Log a Service action: create, patch, delete."""
    return log_action(f"service_{action}", name, namespace, success, error_message=error)


def audit_patch_resource_limits(name: str, namespace: str, container: str, changes: dict, success: bool, error: Optional[str] = None):
    return log_action("deployment_patch_limits", name, namespace, success,
                      details={"container": container, "changes": changes}, error_message=error)


def audit_patch_env_var(name: str, namespace: str, container: str, key: str, success: bool, error: Optional[str] = None):
    return log_action("deployment_patch_env", name, namespace, success,
                      details={"container": container, "key": key}, error_message=error)