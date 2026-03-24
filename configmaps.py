"""
k8s_client/configmaps.py

ConfigMap read and patch operations.

READ:
  - list_configmaps(namespace)         → all configmaps in a namespace
  - get_configmap(name, namespace)     → single configmap content

ACTIONS (require user approval):
  - patch_configmap(name, namespace, data) → update keys in a configmap
"""

import logging
from kubernetes.client.exceptions import ApiException
from .client import get_core_v1

logger = logging.getLogger(__name__)


def list_configmaps(namespace: str = "default") -> list[dict]:
    """List all ConfigMaps in a namespace (names + key counts, not full data)."""
    core = get_core_v1()
    try:
        cm_list = core.list_namespaced_config_map(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list configmaps in {namespace}: {e}")
        raise
    return [
        {
            "name":      cm.metadata.name,
            "namespace": cm.metadata.namespace,
            "keys":      list(cm.data.keys()) if cm.data else [],
        }
        for cm in cm_list.items
    ]


def get_configmap(name: str, namespace: str = "default") -> dict:
    """
    Fetch the full data of a ConfigMap.

    Returns:
        {"name": "my-config", "namespace": "default", "data": {"KEY": "value", ...}}
    """
    core = get_core_v1()
    try:
        cm = core.read_namespaced_config_map(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"ConfigMap {namespace}/{name} not found: {e}")
        raise
    return {
        "name":      cm.metadata.name,
        "namespace": cm.metadata.namespace,
        "data":      cm.data or {},
    }


def patch_configmap(name: str, namespace: str = "default", data: dict = {}) -> dict:
    """
    Add or update keys in a ConfigMap.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      ConfigMap name
        namespace: Namespace
        data:      Dict of key-value pairs to add/update (existing keys not in dict are preserved)

    Returns:
        {"success": bool, "message": str, "updated_keys": list}
    """
    if not data:
        return {"success": False, "message": "No data provided to patch."}

    core = get_core_v1()
    try:
        cm = core.read_namespaced_config_map(name=name, namespace=namespace)
    except ApiException as e:
        return {"success": False, "message": f"ConfigMap not found: {e}"}

    existing = cm.data or {}
    existing.update(data)
    cm.data = existing

    try:
        core.patch_namespaced_config_map(name=name, namespace=namespace, body=cm)
        logger.info(f"[ACTION] Patched ConfigMap {namespace}/{name}: keys={list(data.keys())}")
        return {
            "success":      True,
            "message":      f"ConfigMap {namespace}/{name} updated.",
            "updated_keys": list(data.keys()),
        }
    except ApiException as e:
        logger.error(f"Failed to patch ConfigMap {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}
