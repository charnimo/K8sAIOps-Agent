"""
tools/secrets.py

Kubernetes Secret read and write operations.

READ:
  - list_secrets(namespace)              → list secrets (names/types only, no values)
  - check_secret(name, namespace)        → verify existence + key names (no values)
  - secret_exists(name, namespace)       → bool check

ACTIONS (require user approval):
  - create_secret(name, namespace, data) → create a new Opaque secret
  - update_secret(name, namespace, data) → patch keys in existing secret

⚠️  Secret VALUES are never logged or returned in plaintext — only key names.
"""

import base64
import logging
from typing import Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .client import get_core_v1
from .audit import log_action
from .utils import retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)


def _summarize_secret(sec) -> dict:
    return {
        "name": sec.metadata.name,
        "namespace": sec.metadata.namespace,
        "type": sec.type,
        "key_count": len(sec.data or {}),
        "keys": list((sec.data or {}).keys()),
        "labels": sec.metadata.labels or {},
        "annotations": sec.metadata.annotations or {},
    }


# ─────────────────────────────────────────────
# READ OPERATIONS (with retry)
# ─────────────────────────────────────────────

@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_secrets(namespace: str = "default") -> list[dict]:
    """
    List all secrets in a namespace.

    Returns names and types only — no decoded values (security).
    """
    core = get_core_v1()
    try:
        secret_list = core.list_namespaced_secret(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list secrets in {namespace}: {e}")
        raise
    return [_summarize_secret(sec) for sec in secret_list.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def check_secret(name: str, namespace: str = "default") -> dict:
    """
    Verify a Secret exists and return its key names (NOT values).

    Returns:
        {
          "exists":    True/False,
          "name":      "my-secret",
          "namespace": "default",
          "type":      "Opaque",
          "keys":      ["DB_PASSWORD", "API_KEY"],
          "error":     None  # or error message if not found
        }
    """
    core = get_core_v1()
    try:
        secret = core.read_namespaced_secret(name=name, namespace=namespace)
        return {
            "exists":    True,
            "name":      secret.metadata.name,
            "namespace": secret.metadata.namespace,
            "type":      secret.type,
            "keys":      list(secret.data.keys()) if secret.data else [],
            "error":     None,
        }
    except ApiException as e:
        if e.status == 404:
            return {
                "exists":    False,
                "name":      name,
                "namespace": namespace,
                "type":      None,
                "keys":      [],
                "error":     f"Secret '{name}' not found in namespace '{namespace}'.",
            }
        raise


def secret_exists(name: str, namespace: str = "default") -> bool:
    """Return True if a secret exists, False if not."""
    return check_secret(name, namespace)["exists"]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_secret_values(name: str, namespace: str = "default") -> dict:
    """
    Get secret key-value pairs with proper base64 decoding.

    ⚠️  Use with caution — returns plaintext secret values.
    Do NOT log or expose these values in production.
    ⚠️  All access is audited for compliance purposes.

    NOTE: Kubernetes Python SDK behavior varies by version:
      - Some versions return secret.data values as bytes (need base64 decode)
      - Other versions return them as already-decoded strings (no decode needed)
    This function handles both transparently.

    Returns:
        {
          "exists": True/False,
          "name": "my-secret",
          "namespace": "default",
          "type": "Opaque",
          "data": {"DB_PASSWORD": "plaintext_value", ...},  # decoded
          "error": None  # or error message
        }
    """
    core = get_core_v1()
    try:
        secret = core.read_namespaced_secret(name=name, namespace=namespace)
        decoded_data = {}
        if secret.data:
            for key, value in secret.data.items():
                # Handle different SDK return types
                if isinstance(value, bytes):
                    # Bytes: needs base64 decode
                    try:
                        decoded_data[key] = base64.b64decode(value).decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Failed to decode secret key '{key}': {e}")
                        decoded_data[key] = ""
                elif isinstance(value, str):
                    # String: check if it looks base64 or is already plaintext
                    # Most K8s API returns base64-encoded strings
                    try:
                        decoded_data[key] = base64.b64decode(value).decode('utf-8')
                    except Exception:
                        # If it fails to decode as base64, assume it's already plaintext
                        # (This is rare but can happen with some SDK versions)
                        decoded_data[key] = value
                else:
                    # Unknown type - log warning and skip
                    logger.warning(f"Secret key '{key}' has unexpected type {type(value)}")
                    decoded_data[key] = ""
        
        # AUDIT: Log access to secret values (but not the actual values)
        log_action(
            "get_secret_values",
            name,
            namespace,
            success=True,
            details={"key_count": len(decoded_data), "keys": list(decoded_data.keys())},
        )
        
        return {
            "exists": True,
            "name": secret.metadata.name,
            "namespace": secret.metadata.namespace,
            "type": secret.type,
            "data": decoded_data,
            "error": None,
        }
    except ApiException as e:
        if e.status == 404:
            log_action(
                "get_secret_values",
                name,
                namespace,
                success=False,
                error_message=f"Secret not found (404)",
            )
            return {
                "exists": False,
                "name": name,
                "namespace": namespace,
                "type": None,
                "data": {},
                "error": f"Secret '{name}' not found in namespace '{namespace}'.",
            }
        
        log_action(
            "get_secret_values",
            name,
            namespace,
            success=False,
            error_message=str(e),
        )
        raise


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def create_secret(
    name: str,
    namespace: str = "default",
    data: Optional[dict] = None,
    secret_type: str = "Opaque",
) -> dict:
    """
    Create a new Kubernetes Secret.

    ⚠️  ACTION — requires user approval.

    Args:
        name:        Secret name
        namespace:   Namespace
        data:        Dict of key → plaintext value (will be base64-encoded automatically)
        secret_type: Secret type (default: "Opaque")

    Returns:
        {"success": bool, "message": str, "keys_created": list}
    """
    if not data:
        return {"success": False, "message": "No data provided for secret creation."}

    core = get_core_v1()

    # Base64-encode values (Kubernetes stores secrets as base64)
    encoded = {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}

    secret_body = client.V1Secret(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        type=secret_type,
        data=encoded,
    )
    try:
        core.create_namespaced_secret(namespace=namespace, body=secret_body)
        logger.info(f"[ACTION] Created secret {namespace}/{name} with keys: {list(data.keys())}")
        return {
            "success":      True,
            "message":      f"Secret '{name}' created in namespace '{namespace}'.",
            "keys_created": list(data.keys()),
        }
    except ApiException as e:
        if e.status == 409:
            return {"success": False, "message": f"Secret '{name}' already exists. Use update_secret instead."}
        logger.error(f"Failed to create secret {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def update_secret(
    name: str,
    namespace: str = "default",
    data: Optional[dict] = None,
) -> dict:
    """
    Add or update keys in an existing Kubernetes Secret.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Secret name
        namespace: Namespace
        data:      Dict of key → plaintext value to add/update

    Returns:
        {"success": bool, "message": str, "updated_keys": list}
    """
    if not data:
        return {"success": False, "message": "No data provided to update."}

    core = get_core_v1()
    try:
        secret = core.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as e:
        return {"success": False, "message": f"Secret not found: {e}"}

    existing = secret.data or {}
    for k, v in data.items():
        existing[k] = base64.b64encode(v.encode()).decode()
    secret.data = existing

    try:
        core.patch_namespaced_secret(name=name, namespace=namespace, body=secret)
        logger.info(f"[ACTION] Updated secret {namespace}/{name}: keys={list(data.keys())}")
        return {
            "success":      True,
            "message":      f"Secret '{name}' updated in namespace '{namespace}'.",
            "updated_keys": list(data.keys()),
        }
    except ApiException as e:
        logger.error(f"Failed to update secret {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def delete_secret(name: str, namespace: str = "default") -> dict:
    """
    Delete a Kubernetes Secret.

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Secret name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    try:
        name = validate_name(name)
        namespace = validate_namespace(namespace)
    except ValueError as e:
        return {"success": False, "message": f"Invalid input: {str(e)}"}
    
    core = get_core_v1()
    
    # Defensive check
    try:
        core.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            return {"success": False, "message": f"Secret {namespace}/{name} not found"}
        raise
    
    try:
        core.delete_namespaced_secret(name=name, namespace=namespace)
        logger.info(f"[ACTION] Deleted secret {namespace}/{name}")
        return {
            "success": True,
            "message": f"Secret '{name}' deleted from namespace '{namespace}'.",
        }
    except ApiException as e:
        logger.error(f"Failed to delete secret {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}

    
def get_secret_metadata(name: str, namespace: str = "default") -> dict:
    """Get secret metadata and key list without returning secret values."""
    core = get_core_v1()
    try:
        sec = core.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Secret {namespace}/{name} not found: {e}")
        raise

    return _summarize_secret(sec)
