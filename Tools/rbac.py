"""
Tools/rbac.py

RBAC inspection — read-only.

The agent needs to understand RBAC to:
  - Diagnose "permission denied" errors in application logs
  - Verify the agent's own ServiceAccount permissions
  - Audit what permissions exist in a namespace

READ:
  - list_roles(namespace)                            → Roles in a namespace
  - list_cluster_roles()                             → ClusterRoles cluster-wide
  - list_role_bindings(namespace)                    → RoleBindings in a namespace
  - list_cluster_role_bindings()                     → ClusterRoleBindings cluster-wide
  - get_service_account_permissions(sa, namespace)   → what can a ServiceAccount do
  - check_permission(sa, namespace, verb, resource)  → can SA do X on Y?
"""

import logging
from typing import Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from .client import get_core_v1

logger = logging.getLogger(__name__)


def _get_rbac_v1():
    from .client import _init_client
    _init_client()
    return client.RbacAuthorizationV1Api()


def _get_auth_v1():
    from .client import _init_client
    _init_client()
    return client.AuthorizationV1Api()


# ─────────────────────────────────────────────
# ROLE / CLUSTERROLE LISTING
# ─────────────────────────────────────────────

def list_roles(namespace: str = "default") -> list[dict]:
    """
    List all Roles in a namespace.

    Returns:
        [{"name": str, "namespace": str, "rules": [...]}]
    """
    rbac = _get_rbac_v1()
    try:
        role_list = rbac.list_namespaced_role(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list roles in {namespace}: {e}")
        raise
    return [_summarize_role(r) for r in role_list.items]


def list_cluster_roles() -> list[dict]:
    """
    List all ClusterRoles.

    Filters out system-managed roles (prefixed with 'system:') by default
    to keep the output manageable.
    """
    rbac = _get_rbac_v1()
    try:
        cr_list = rbac.list_cluster_role()
    except ApiException as e:
        logger.error(f"Failed to list cluster roles: {e}")
        raise
    return [
        _summarize_role(r) for r in cr_list.items
        if not r.metadata.name.startswith("system:")
    ]


def list_role_bindings(namespace: str = "default") -> list[dict]:
    """
    List all RoleBindings in a namespace, showing what subjects have what roles.

    Returns:
        [{"name": str, "role": str, "subjects": [{"kind": str, "name": str}]}]
    """
    rbac = _get_rbac_v1()
    try:
        rb_list = rbac.list_namespaced_role_binding(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list role bindings in {namespace}: {e}")
        raise
    return [_summarize_binding(rb) for rb in rb_list.items]


def list_cluster_role_bindings() -> list[dict]:
    """
    List all ClusterRoleBindings, filtering out system-managed ones.
    """
    rbac = _get_rbac_v1()
    try:
        crb_list = rbac.list_cluster_role_binding()
    except ApiException as e:
        logger.error(f"Failed to list cluster role bindings: {e}")
        raise
    return [
        _summarize_binding(crb) for crb in crb_list.items
        if not crb.metadata.name.startswith("system:")
    ]


# ─────────────────────────────────────────────
# SERVICEACCOUNT PERMISSION INSPECTION
# ─────────────────────────────────────────────

def get_service_account_permissions(
    service_account: str,
    namespace: str = "default",
) -> dict:
    """
    Summarize what permissions a ServiceAccount has by inspecting all
    RoleBindings and ClusterRoleBindings that reference it.

    This is a static analysis — it reads bindings and resolves roles,
    it does NOT use the SubjectAccessReview API.

    Args:
        service_account: ServiceAccount name
        namespace:        Namespace of the ServiceAccount

    Returns:
        {
          "service_account": str,
          "namespace": str,
          "exists": bool,
          "bindings": [          # every binding that grants it permissions
            {
              "binding_name": str,
              "binding_kind": "RoleBinding" | "ClusterRoleBinding",
              "role_name": str,
              "role_kind": "Role" | "ClusterRole",
              "rules": [...]
            }
          ],
          "all_rules": [...]    # flattened deduplicated rules across all bindings
        }
    """
    core = get_core_v1()
    rbac = _get_rbac_v1()

    # Verify the ServiceAccount exists
    sa_exists = True
    try:
        core.read_namespaced_service_account(name=service_account, namespace=namespace)
    except ApiException as e:
        if e.status == 404:
            sa_exists = False
        else:
            raise

    result = {
        "service_account": service_account,
        "namespace":       namespace,
        "exists":          sa_exists,
        "bindings":        [],
        "all_rules":       [],
    }

    if not sa_exists:
        return result

    def _sa_in_subjects(subjects) -> bool:
        if not subjects:
            return False
        for s in subjects:
            if (s.kind == "ServiceAccount"
                    and s.name == service_account
                    and s.namespace == namespace):
                return True
        return False

    # Check namespaced RoleBindings
    try:
        rb_list = rbac.list_namespaced_role_binding(namespace=namespace)
        for rb in rb_list.items:
            if not _sa_in_subjects(rb.subjects):
                continue
            rules = _resolve_role_rules(rbac, rb.role_ref, namespace)
            result["bindings"].append({
                "binding_name": rb.metadata.name,
                "binding_kind": "RoleBinding",
                "role_name":    rb.role_ref.name,
                "role_kind":    rb.role_ref.kind,
                "rules":        rules,
            })
    except ApiException as e:
        logger.warning(f"Could not list RoleBindings in {namespace}: {e}")

    # Check ClusterRoleBindings
    try:
        crb_list = rbac.list_cluster_role_binding()
        for crb in crb_list.items:
            if not _sa_in_subjects(crb.subjects):
                continue
            rules = _resolve_role_rules(rbac, crb.role_ref, namespace)
            result["bindings"].append({
                "binding_name": crb.metadata.name,
                "binding_kind": "ClusterRoleBinding",
                "role_name":    crb.role_ref.name,
                "role_kind":    crb.role_ref.kind,
                "rules":        rules,
            })
    except ApiException as e:
        logger.warning(f"Could not list ClusterRoleBindings: {e}")

    # Flatten all rules (deduplicated by string representation)
    seen = set()
    all_rules = []
    for binding in result["bindings"]:
        for rule in binding["rules"]:
            key = str(rule)
            if key not in seen:
                seen.add(key)
                all_rules.append(rule)
    result["all_rules"] = all_rules

    return result


def check_permission(
    service_account: str,
    namespace: str,
    verb: str,
    resource: str,
    resource_namespace: Optional[str] = None,
) -> dict:
    """
    Check if a ServiceAccount can perform a specific verb on a resource.

    Uses the SubjectAccessReview API — the authoritative way to check permissions
    (respects admission webhooks, aggregated ClusterRoles, etc.)

    Args:
        service_account:      SA name
        namespace:            SA namespace
        verb:                 e.g. "get", "list", "create", "delete", "patch"
        resource:             e.g. "pods", "deployments", "secrets"
        resource_namespace:   Namespace to check in (defaults to SA namespace)

    Returns:
        {
          "allowed": bool,
          "reason":  str,
          "verb":    str,
          "resource": str,
        }
    """
    auth = _get_auth_v1()
    check_ns = resource_namespace or namespace

    sar_body = client.V1SubjectAccessReview(
        spec=client.V1SubjectAccessReviewSpec(
            user=f"system:serviceaccount:{namespace}:{service_account}",
            resource_attributes=client.V1ResourceAttributes(
                namespace=check_ns,
                verb=verb,
                resource=resource,
            ),
        )
    )

    try:
        result = auth.create_subject_access_review(body=sar_body)
        return {
            "allowed":   result.status.allowed,
            "reason":    result.status.reason or "",
            "verb":      verb,
            "resource":  resource,
            "namespace": check_ns,
        }
    except ApiException as e:
        logger.error(f"SubjectAccessReview failed: {e}")
        return {
            "allowed":  False,
            "reason":   f"API error: {e.reason}",
            "verb":     verb,
            "resource": resource,
        }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_role(role) -> dict:
    rules = []
    for rule in (role.rules or []):
        rules.append({
            "verbs":           rule.verbs or [],
            "api_groups":      rule.api_groups or [],
            "resources":       rule.resources or [],
            "resource_names":  rule.resource_names or [],
        })
    return {
        "name":      role.metadata.name,
        "namespace": getattr(role.metadata, "namespace", None),
        "rules":     rules,
    }


def _summarize_binding(binding) -> dict:
    subjects = []
    for s in (binding.subjects or []):
        subjects.append({
            "kind":      s.kind,
            "name":      s.name,
            "namespace": getattr(s, "namespace", None),
        })
    return {
        "name":      binding.metadata.name,
        "namespace": getattr(binding.metadata, "namespace", None),
        "role_ref":  {
            "kind": binding.role_ref.kind,
            "name": binding.role_ref.name,
        },
        "subjects": subjects,
    }


def _resolve_role_rules(rbac, role_ref, namespace: str) -> list[dict]:
    """Fetch the rules from a Role or ClusterRole reference."""
    try:
        if role_ref.kind == "ClusterRole":
            role = rbac.read_cluster_role(name=role_ref.name)
        else:
            role = rbac.read_namespaced_role(name=role_ref.name, namespace=namespace)

        rules = []
        for rule in (role.rules or []):
            rules.append({
                "verbs":     rule.verbs or [],
                "resources": rule.resources or [],
                "api_groups": rule.api_groups or [],
            })
        return rules
    except ApiException:
        return []
