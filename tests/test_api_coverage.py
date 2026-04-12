"""Static coverage checks for exposed tool surfaces."""

from app.main import app
from app.services.actions import ACTION_HANDLERS


EXPECTED_TOOL_PATHS = {
    "/",
    "/dashboard/summary",
    "/events",
    "/resources/pods",
    "/resources/deployments",
    "/resources/services",
    "/workloads/statefulsets",
    "/workloads/daemonsets",
    "/workloads/jobs",
    "/workloads/cronjobs",
    "/cluster/nodes",
    "/cluster/namespaces",
    "/cluster/storage/pvs",
    "/cluster/storage/pvcs",
    "/cluster/storage/classes",
    "/config/configmaps",
    "/config/secrets",
    "/config/ingresses",
    "/config/network-policies",
    "/governance/service-accounts",
    "/governance/roles",
    "/governance/cluster-roles",
    "/governance/role-bindings",
    "/governance/cluster-role-bindings",
    "/governance/hpas",
    "/governance/resource-quotas",
    "/governance/limit-ranges",
    "/observability/metrics/pods",
    "/observability/metrics/nodes",
    "/observability/resource-pressure",
    "/diagnostics/pods",
    "/diagnostics/deployments",
    "/diagnostics/services",
    "/diagnostics/cluster",
    "/action-requests",
    "/action-types",
    "/audit-logs",
    "/resources/pods/{name}/exec",
    "/resources/deployments/{name}/scale",
    "/resources/deployments/{name}/restart",
    "/resources/deployments/{name}/rollback",
    "/resources/deployments/{name}/resource-limits",
    "/resources/deployments/{name}/env",
    "/config/configmaps/{name}",
    "/config/ingresses/{name}",
}


EXPECTED_DIRECT_ROUTE_METHODS = {
    "/resources/pods/{name}": {"get", "delete"},
    "/resources/pods/{name}/exec": {"post"},
    "/resources/deployments/{name}/scale": {"patch"},
    "/resources/deployments/{name}/restart": {"post"},
    "/resources/deployments/{name}/rollback": {"post"},
    "/resources/deployments/{name}/resource-limits": {"patch"},
    "/resources/deployments/{name}/env": {"patch"},
    "/resources/services": {"get", "post"},
    "/resources/services/{name}": {"get", "patch", "delete"},
    "/config/configmaps": {"get", "post"},
    "/config/configmaps/{name}": {"get", "patch", "delete"},
    "/config/secrets": {"get", "post"},
    "/config/secrets/{name}": {"get", "patch", "delete"},
    "/config/ingresses": {"get", "post"},
    "/config/ingresses/{name}": {"get", "patch", "delete"},
}


EXPECTED_ACTION_TYPES = {
    "delete_pod",
    "exec_pod",
    "scale_deployment",
    "restart_deployment",
    "rollback_deployment",
    "patch_resource_limits",
    "patch_env_var",
    "scale_statefulset",
    "restart_statefulset",
    "restart_daemonset",
    "update_daemonset_image",
    "delete_job",
    "suspend_job",
    "suspend_cronjob",
    "resume_cronjob",
    "create_service",
    "patch_service",
    "delete_service",
    "create_configmap",
    "patch_configmap",
    "delete_configmap",
    "create_secret",
    "update_secret",
    "delete_secret",
    "cordon_node",
    "uncordon_node",
    "drain_node",
    "create_pvc",
    "patch_pvc",
    "delete_pvc",
    "create_ingress",
    "patch_ingress",
    "delete_ingress",
    "create_hpa",
    "patch_hpa",
    "delete_hpa",
}


def test_openapi_covers_public_tool_surfaces():
    """The API should expose a representative route for each public tool area."""
    paths = set(app.openapi()["paths"])
    assert EXPECTED_TOOL_PATHS <= paths


def test_action_registry_covers_mutating_tools():
    """Approved action execution should cover the supported mutating tools."""
    assert set(ACTION_HANDLERS) == EXPECTED_ACTION_TYPES


def test_openapi_exposes_direct_mutation_methods():
    """The direct API should expose verb-level coverage for core tool mutations."""
    paths = app.openapi()["paths"]
    for path, methods in EXPECTED_DIRECT_ROUTE_METHODS.items():
        assert methods <= set(paths[path])
