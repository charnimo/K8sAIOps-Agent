"""
tools/rbac.py

Kubernetes RBAC resource operations (Roles, RoleBindings, ClusterRoles, ClusterRoleBindings, ServiceAccounts).

Operations:
  READ:  list_service_accounts, get_service_account, list_roles, get_role,
         list_cluster_roles, get_cluster_role, list_role_bindings, get_role_binding,
         list_cluster_role_bindings, get_cluster_role_binding
"""

import logging
from typing import Optional

from kubernetes.client.exceptions import ApiException

from .client import get_rbac_v1, get_core_v1
from .utils import fmt_time, retry_on_transient

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SERVICE ACCOUNTS
# ─────────────────────────────────────────────

def list_service_accounts(namespace: str = "default") -> list[dict]:
    """List ServiceAccounts in a namespace."""
    try:
        v1 = get_core_v1()
        sas = v1.list_namespaced_service_account(namespace)
        return [_summarize_service_account(sa) for sa in sas.items]
    except ApiException as e:
        logger.error(f"Failed to list ServiceAccounts in {namespace}: {e}")
        return []


def list_all_service_accounts() -> list[dict]:
    """List all ServiceAccounts across all namespaces."""
    try:
        v1 = get_core_v1()
        sas = v1.list_service_account_for_all_namespaces()
        return [_summarize_service_account(sa) for sa in sas.items]
    except ApiException as e:
        logger.error(f"Failed to list all ServiceAccounts: {e}")
        return []


def get_service_account(name: str, namespace: str = "default") -> dict:
    """Get a single ServiceAccount."""
    try:
        v1 = get_core_v1()
        sa = v1.read_namespaced_service_account(name, namespace)
        return _summarize_service_account(sa)
    except ApiException as e:
        logger.error(f"Failed to get ServiceAccount {namespace}/{name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# ROLES (namespace-scoped)
# ─────────────────────────────────────────────

def list_roles(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """List Roles in a namespace."""
    try:
        rbac_api = get_rbac_v1()
        roles = rbac_api.list_namespaced_role(namespace, label_selector=label_selector)
        return [_summarize_role(role) for role in roles.items]
    except ApiException as e:
        logger.error(f"Failed to list Roles in {namespace}: {e}")
        return []


def get_role(name: str, namespace: str = "default") -> dict:
    """Get a single Role."""
    try:
        rbac_api = get_rbac_v1()
        role = rbac_api.read_namespaced_role(name, namespace)
        return _summarize_role(role)
    except ApiException as e:
        logger.error(f"Failed to get Role {namespace}/{name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# CLUSTER ROLES (cluster-wide)
# ─────────────────────────────────────────────

def list_cluster_roles(label_selector: Optional[str] = None) -> list[dict]:
    """List all ClusterRoles in the cluster."""
    try:
        rbac_api = get_rbac_v1()
        cluster_roles = rbac_api.list_cluster_role(label_selector=label_selector)
        return [_summarize_cluster_role(cr) for cr in cluster_roles.items]
    except ApiException as e:
        logger.error(f"Failed to list ClusterRoles: {e}")
        return []


def get_cluster_role(name: str) -> dict:
    """Get a single ClusterRole."""
    try:
        rbac_api = get_rbac_v1()
        cluster_role = rbac_api.read_cluster_role(name)
        return _summarize_cluster_role(cluster_role)
    except ApiException as e:
        logger.error(f"Failed to get ClusterRole {name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# ROLE BINDINGS (namespace-scoped)
# ─────────────────────────────────────────────

def list_role_bindings(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """List RoleBindings in a namespace."""
    try:
        rbac_api = get_rbac_v1()
        bindings = rbac_api.list_namespaced_role_binding(namespace, label_selector=label_selector)
        return [_summarize_role_binding(binding) for binding in bindings.items]
    except ApiException as e:
        logger.error(f"Failed to list RoleBindings in {namespace}: {e}")
        return []


def get_role_binding(name: str, namespace: str = "default") -> dict:
    """Get a single RoleBinding."""
    try:
        rbac_api = get_rbac_v1()
        binding = rbac_api.read_namespaced_role_binding(name, namespace)
        return _summarize_role_binding(binding)
    except ApiException as e:
        logger.error(f"Failed to get RoleBinding {namespace}/{name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# CLUSTER ROLE BINDINGS (cluster-wide)
# ─────────────────────────────────────────────

def list_cluster_role_bindings(label_selector: Optional[str] = None) -> list[dict]:
    """List all ClusterRoleBindings in the cluster."""
    try:
        rbac_api = get_rbac_v1()
        bindings = rbac_api.list_cluster_role_binding(label_selector=label_selector)
        return [_summarize_cluster_role_binding(binding) for binding in bindings.items]
    except ApiException as e:
        logger.error(f"Failed to list ClusterRoleBindings: {e}")
        return []


def get_cluster_role_binding(name: str) -> dict:
    """Get a single ClusterRoleBinding."""
    try:
        rbac_api = get_rbac_v1()
        binding = rbac_api.read_cluster_role_binding(name)
        return _summarize_cluster_role_binding(binding)
    except ApiException as e:
        logger.error(f"Failed to get ClusterRoleBinding {name}: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_service_account(sa) -> dict:
    """Convert ServiceAccount to clean dict."""
    age = fmt_time(sa.metadata.creation_timestamp) if sa.metadata.creation_timestamp else None

    return {
        "name": sa.metadata.name,
        "namespace": sa.metadata.namespace,
        "automount_token": sa.automount_service_account_token if sa else True,
        "image_pull_secrets": [s.name for s in (sa.image_pull_secrets or [])] if sa else [],
        "age": age,
        "labels": sa.metadata.labels or {},
    }


def _summarize_role(role) -> dict:
    """Convert Role to clean dict."""
    rules = []
    if role.rules:
        for rule in role.rules:
            rules.append(
                {
                    "api_groups": rule.api_groups or [""],
                    "resources": rule.resources or [],
                    "verbs": rule.verbs or [],
                }
            )

    age = fmt_time(role.metadata.creation_timestamp) if role.metadata.creation_timestamp else None

    return {
        "name": role.metadata.name,
        "namespace": role.metadata.namespace,
        "rule_count": len(rules),
        "rules": rules,
        "age": age,
        "labels": role.metadata.labels or {},
    }


def _summarize_cluster_role(cr) -> dict:
    """Convert ClusterRole to clean dict."""
    rules = []
    if cr.rules:
        for rule in cr.rules:
            rules.append(
                {
                    "api_groups": rule.api_groups or [""],
                    "resources": rule.resources or [],
                    "verbs": rule.verbs or [],
                }
            )

    age = fmt_time(cr.metadata.creation_timestamp) if cr.metadata.creation_timestamp else None

    return {
        "name": cr.metadata.name,
        "rule_count": len(rules),
        "rules": rules,
        "age": age,
        "labels": cr.metadata.labels or {},
    }


def _summarize_role_binding(binding) -> dict:
    """Convert RoleBinding to clean dict."""
    subjects = []
    if binding.subjects:
        for subj in binding.subjects:
            subjects.append(
                {"kind": subj.kind, "name": subj.name, "namespace": subj.namespace or "N/A"}
            )

    role_ref = binding.role_ref or {}

    age = fmt_time(binding.metadata.creation_timestamp) if binding.metadata.creation_timestamp else None

    return {
        "name": binding.metadata.name,
        "namespace": binding.metadata.namespace,
        "role": f"{role_ref.kind}/{role_ref.name}" if role_ref else "N/A",
        "subject_count": len(subjects),
        "subjects": subjects,
        "age": age,
        "labels": binding.metadata.labels or {},
    }


def _summarize_cluster_role_binding(binding) -> dict:
    """Convert ClusterRoleBinding to clean dict."""
    subjects = []
    if binding.subjects:
        for subj in binding.subjects:
            subjects.append(
                {"kind": subj.kind, "name": subj.name, "namespace": subj.namespace or "cluster-wide"}
            )

    role_ref = binding.role_ref or {}

    age = fmt_time(binding.metadata.creation_timestamp) if binding.metadata.creation_timestamp else None

    return {
        "name": binding.metadata.name,
        "role": f"{role_ref.kind}/{role_ref.name}" if role_ref else "N/A",
        "subject_count": len(subjects),
        "subjects": subjects,
        "age": age,
        "labels": binding.metadata.labels or {},
    }
