"""Basic API tests for the FastAPI scaffold."""

from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException

from app.api import mutations as mutation_helpers
from app.api.routes import cluster as cluster_routes
from app.api.routes import configuration as configuration_routes
from app.api.routes import diagnostics as diagnostics_routes
from app.api.routes import governance as governance_routes
from app.api.routes import resources as resources_routes
from app.api.routes import workloads as workloads_routes
from fastapi.testclient import TestClient

from app.main import app
from app.state.store import get_action_request, mark_action_request_executed


client = TestClient(app)


def test_root_endpoint_points_to_docs():
    """Root endpoint should provide a friendly API entrypoint."""
    response = client.get("/")
    assert response.status_code == 200

    payload = response.json()
    assert payload["docs_url"] == "/docs"
    assert payload["health_url"] == "/health"


def test_favicon_endpoint_returns_no_content():
    """Favicon requests should not produce browser-facing 404 noise."""
    response = client.get("/favicon.ico")
    assert response.status_code == 204
    assert response.content == b""


def test_health_endpoint():
    """Health endpoint should expose service metadata and runtime flags."""
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert "read_only_mode" in payload
    assert "mutations_enabled" in payload


def test_create_and_fetch_chat_session():
    """Chat sessions should be created and readable without cluster access."""
    create_response = client.post("/chat/sessions")
    assert create_response.status_code == 200

    session = create_response.json()
    session_id = session["id"]
    assert session["messages"] == []

    fetch_response = client.get(f"/chat/sessions/{session_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["id"] == session_id


def test_post_chat_message_leaves_assistant_empty():
    """Posting a chat message should not invent an assistant reply."""
    session_id = client.post("/chat/sessions").json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Why is my pod crashing?"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"] is None
    assert len(payload["session"]["messages"]) == 1


def test_create_action_request_defaults_to_pending():
    """New action requests should start in pending status."""
    response = client.post(
        "/action-requests",
        json={
            "type": "scale_deployment",
            "target": {"name": "api", "namespace": "default"},
            "params": {"replicas": 3},
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["type"] == "scale_deployment"


def test_list_action_requests_includes_created_record():
    """Action request listing should expose newly created requests."""
    created = client.post(
        "/action-requests",
        json={
            "type": "delete_pod",
            "target": {"name": "api-pod", "namespace": "default"},
            "params": {},
        },
    ).json()

    response = client.get("/action-requests")
    assert response.status_code == 200

    records = response.json()
    assert any(record["id"] == created["id"] for record in records)


def test_action_types_endpoint_lists_supported_actions():
    """Supported action types should be discoverable for the frontend."""
    response = client.get("/action-types")
    assert response.status_code == 200

    payload = response.json()
    assert "scale_deployment" in payload["action_types"]
    assert "create_configmap" in payload["action_types"]


def test_secret_values_endpoint_requires_explicit_opt_in(monkeypatch):
    """Plaintext secret reads should stay disabled unless explicitly enabled."""
    monkeypatch.setattr(
        configuration_routes,
        "get_settings",
        lambda: SimpleNamespace(allow_plaintext_secret_reads=False),
    )
    monkeypatch.setattr(
        configuration_routes.secrets,
        "get_secret_values",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("secret reads should be blocked")),
    )

    response = client.get("/config/secrets/api-keys/values")
    assert response.status_code == 403
    assert "AIOPS_ALLOW_PLAINTEXT_SECRET_READS=true" in response.json()["detail"]


def test_secret_values_endpoint_allows_explicit_opt_in(monkeypatch):
    """Trusted deployments can still opt in to plaintext secret reads."""
    monkeypatch.setattr(
        configuration_routes,
        "get_settings",
        lambda: SimpleNamespace(allow_plaintext_secret_reads=True),
    )
    monkeypatch.setattr(
        configuration_routes.secrets,
        "get_secret_values",
        lambda name, namespace: {"name": name, "namespace": namespace, "data": {"token": "plaintext"}},
    )

    response = client.get("/config/secrets/api-keys/values", params={"namespace": "ops"})
    assert response.status_code == 200
    assert response.json()["data"]["token"] == "plaintext"


def test_network_policy_issues_route_is_not_shadowed(monkeypatch):
    """The static /issues route should win over the {name} route."""
    monkeypatch.setattr(
        configuration_routes.network_policies,
        "detect_network_issues",
        lambda namespace: {"route": "issues", "namespace": namespace},
    )
    monkeypatch.setattr(
        configuration_routes.network_policies,
        "get_network_policy",
        lambda name, namespace: {"route": "named", "name": name, "namespace": namespace},
    )

    response = client.get("/config/network-policies/issues", params={"namespace": "team-a"})
    assert response.status_code == 200
    assert response.json() == {"route": "issues", "namespace": "team-a"}


def test_reject_action_conflicts_when_request_is_not_pending():
    """Reject should preserve completed action history instead of rewriting it."""
    created = client.post(
        "/action-requests",
        json={
            "type": "delete_pod",
            "target": {"name": "api-pod", "namespace": "default"},
            "params": {},
        },
    ).json()
    mark_action_request_executed(created["id"], result={"success": True})

    response = client.post(f"/action-requests/{created['id']}/reject")
    assert response.status_code == 409
    assert response.json()["detail"] == "Action request is not pending"

    record = get_action_request(created["id"])
    assert record["status"] == "completed"
    assert record["result"] == {"success": True}


def test_missing_pod_lookup_returns_404(monkeypatch):
    """Missing pods should surface as not found rather than generic server errors."""
    monkeypatch.setattr(
        resources_routes.pods,
        "get_pod_status",
        lambda name, namespace: (_ for _ in ()).throw(ApiException(status=404, reason="Not Found")),
    )

    response = client.get("/resources/pods/missing-pod", params={"namespace": "default"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Pod 'missing-pod' not found in namespace 'default'"


def test_delete_pod_direct_route_calls_action(monkeypatch):
    """DELETE pod routes should dispatch through the shared action executor."""
    calls = []
    monkeypatch.setattr(
        resources_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.delete("/resources/pods/api-pod", params={"namespace": "ops"})
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert calls == [("delete_pod", {"name": "api-pod", "namespace": "ops"})]


def test_exec_pod_direct_route_passes_payload(monkeypatch):
    """Pod exec routes should preserve command and stream flags."""
    calls = []
    monkeypatch.setattr(
        resources_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/resources/pods/api-pod/exec?namespace=ops",
        json={"command": ["sh", "-c", "env"], "stdin": False, "stdout": True, "stderr": True, "tty": False},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "exec_pod",
            {
                "name": "api-pod",
                "namespace": "ops",
                "params": {
                    "command": ["sh", "-c", "env"],
                    "stdin": False,
                    "stdout": True,
                    "stderr": True,
                    "tty": False,
                },
            },
        )
    ]


def test_scale_deployment_direct_route_calls_action(monkeypatch):
    """Deployment scale routes should translate PATCH payloads into action params."""
    calls = []
    monkeypatch.setattr(
        resources_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.patch("/resources/deployments/api/scale?namespace=ops", json={"replicas": 4})
    assert response.status_code == 200
    assert calls == [("scale_deployment", {"name": "api", "namespace": "ops", "params": {"replicas": 4}})]


def test_create_service_direct_route_calls_action(monkeypatch):
    """Service creation routes should preserve the request body fields."""
    calls = []
    monkeypatch.setattr(
        resources_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/resources/services",
        json={
            "name": "api-svc",
            "namespace": "ops",
            "service_type": "ClusterIP",
            "selector": {"app": "api"},
            "ports": [{"port": 80, "target_port": 8080, "protocol": "TCP", "name": "http"}],
            "labels": {"team": "platform"},
        },
    )
    assert response.status_code == 200
    assert calls == [
        (
            "create_service",
            {
                "name": "api-svc",
                "namespace": "ops",
                "params": {
                    "service_type": "ClusterIP",
                    "selector": {"app": "api"},
                    "ports": [{"port": 80, "target_port": 8080, "protocol": "TCP", "name": "http"}],
                    "labels": {"team": "platform"},
                },
            },
        )
    ]


def test_create_configmap_direct_route_calls_action(monkeypatch):
    """ConfigMap creation routes should dispatch direct create actions."""
    calls = []
    monkeypatch.setattr(
        configuration_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/config/configmaps",
        json={"name": "app-config", "namespace": "ops", "data": {"LOG_LEVEL": "debug"}, "labels": {"app": "api"}},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "create_configmap",
            {
                "name": "app-config",
                "namespace": "ops",
                "params": {"data": {"LOG_LEVEL": "debug"}, "labels": {"app": "api"}},
            },
        )
    ]


def test_update_secret_direct_route_calls_action(monkeypatch):
    """Secret update routes should preserve namespace and data."""
    calls = []
    monkeypatch.setattr(
        configuration_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.patch(
        "/config/secrets/api-secret",
        json={"namespace": "ops", "data": {"TOKEN": "new-value"}},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "update_secret",
            {
                "name": "api-secret",
                "namespace": "ops",
                "params": {"data": {"TOKEN": "new-value"}},
            },
        )
    ]


def test_create_ingress_direct_route_calls_action(monkeypatch):
    """Ingress creation routes should preserve rules, tls, and metadata."""
    calls = []
    monkeypatch.setattr(
        configuration_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/config/ingresses",
        json={
            "name": "api-ing",
            "namespace": "ops",
            "rules": [{"host": "api.example.com", "paths": [{"path": "/", "service": "api-svc", "port": 80}]}],
            "tls": [{"hosts": ["api.example.com"], "secret_name": "tls-secret"}],
            "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"},
            "labels": {"app": "api"},
        },
    )
    assert response.status_code == 200
    assert calls == [
        (
            "create_ingress",
            {
                "name": "api-ing",
                "namespace": "ops",
                "params": {
                    "rules": [{"host": "api.example.com", "paths": [{"path": "/", "service": "api-svc", "port": 80}]}],
                    "tls": [{"hosts": ["api.example.com"], "secret_name": "tls-secret"}],
                    "annotations": {"nginx.ingress.kubernetes.io/rewrite-target": "/"},
                    "labels": {"app": "api"},
                },
            },
        )
    ]


def test_direct_mutation_helper_respects_runtime_flags(monkeypatch):
    """Direct mutation helpers should honor the same runtime flags as approvals."""
    monkeypatch.setattr(
        mutation_helpers,
        "get_settings",
        lambda: SimpleNamespace(read_only_mode=True, mutations_enabled=False),
    )

    response = client.delete("/resources/pods/api-pod")
    assert response.status_code == 409
    assert "Mutations are disabled" in response.json()["detail"]


def test_scale_statefulset_direct_route_calls_action(monkeypatch):
    """StatefulSet scale routes should translate PATCH payloads into action params."""
    calls = []
    monkeypatch.setattr(
        workloads_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.patch("/workloads/statefulsets/db/scale?namespace=ops", json={"replicas": 2})
    assert response.status_code == 200
    assert calls == [("scale_statefulset", {"name": "db", "namespace": "ops", "params": {"replicas": 2}})]


def test_update_daemonset_image_direct_route_calls_action(monkeypatch):
    """DaemonSet image routes should preserve container and image fields."""
    calls = []
    monkeypatch.setattr(
        workloads_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.patch(
        "/workloads/daemonsets/agent/image",
        json={"namespace": "ops", "container": "agent", "image": "repo/agent:v2"},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "update_daemonset_image",
            {
                "name": "agent",
                "namespace": "ops",
                "params": {"container": "agent", "image": "repo/agent:v2"},
            },
        )
    ]


def test_delete_job_direct_route_calls_action(monkeypatch):
    """Job delete routes should pass propagation policy through to the action layer."""
    calls = []
    monkeypatch.setattr(
        workloads_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.delete(
        "/workloads/jobs/data-backfill",
        params={"namespace": "ops", "propagation_policy": "Background"},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "delete_job",
            {
                "name": "data-backfill",
                "namespace": "ops",
                "params": {"propagation_policy": "Background"},
            },
        )
    ]


def test_drain_node_direct_route_calls_action(monkeypatch):
    """Node drain routes should preserve the drain options payload."""
    calls = []
    monkeypatch.setattr(
        cluster_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/cluster/nodes/worker-1/drain",
        json={"ignore_daemonsets": False, "grace_period_seconds": 15},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "drain_node",
            {
                "name": "worker-1",
                "params": {"ignore_daemonsets": False, "grace_period_seconds": 15},
            },
        )
    ]


def test_create_pvc_direct_route_calls_action(monkeypatch):
    """PVC creation routes should preserve storage-related fields."""
    calls = []
    monkeypatch.setattr(
        cluster_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.post(
        "/cluster/storage/pvcs",
        json={
            "name": "data",
            "namespace": "ops",
            "size": "20Gi",
            "access_modes": ["ReadWriteOnce"],
            "storage_class": "fast-ssd",
            "labels": {"app": "db"},
        },
    )
    assert response.status_code == 200
    assert calls == [
        (
            "create_pvc",
            {
                "name": "data",
                "namespace": "ops",
                "params": {
                    "size": "20Gi",
                    "access_modes": ["ReadWriteOnce"],
                    "storage_class": "fast-ssd",
                    "labels": {"app": "db"},
                },
            },
        )
    ]


def test_patch_hpa_direct_route_calls_action(monkeypatch):
    """HPA patch routes should preserve replica and label updates."""
    calls = []
    monkeypatch.setattr(
        governance_routes,
        "run_direct_action",
        lambda action_type, **kwargs: calls.append((action_type, kwargs)) or {"success": True},
    )

    response = client.patch(
        "/governance/hpas/api-hpa",
        json={"namespace": "ops", "min_replicas": 2, "max_replicas": 8, "labels": {"team": "platform"}},
    )
    assert response.status_code == 200
    assert calls == [
        (
            "patch_hpa",
            {
                "name": "api-hpa",
                "namespace": "ops",
                "params": {"min_replicas": 2, "max_replicas": 8, "labels": {"team": "platform"}},
            },
        )
    ]


def test_get_pod_diagnostics_variant_uses_query_params(monkeypatch):
    """GET diagnostics should support quick browser testing via query params."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_pod",
        lambda name, namespace: {"target": {"name": name, "namespace": namespace}},
    )

    response = client.get("/diagnostics/pods", params={"name": "crashloop-test", "namespace": "default"})
    assert response.status_code == 200
    assert response.json()["target"]["name"] == "crashloop-test"


def test_get_deployment_diagnostics_variant_accepts_flags(monkeypatch):
    """GET deployment diagnostics should pass query flags through to the tool."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_deployment",
        lambda name, namespace, include_pod_details, include_resource_pressure: {
            "target": {"name": name, "namespace": namespace},
            "flags": {
                "include_pod_details": include_pod_details,
                "include_resource_pressure": include_resource_pressure,
            },
        },
    )

    response = client.get(
        "/diagnostics/deployments",
        params={
            "name": "nginx-test",
            "namespace": "default",
            "include_pod_details": "true",
            "include_resource_pressure": "true",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["target"]["name"] == "nginx-test"
    assert payload["flags"]["include_pod_details"] is True
    assert payload["flags"]["include_resource_pressure"] is True


def test_get_service_diagnostics_variant_uses_query_params(monkeypatch):
    """GET service diagnostics should support simple browser-driven checks."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_service",
        lambda name, namespace: {"target": {"name": name, "namespace": namespace}},
    )

    response = client.get("/diagnostics/services", params={"name": "nginx-test-svc", "namespace": "default"})
    assert response.status_code == 200
    assert response.json()["target"]["name"] == "nginx-test-svc"
